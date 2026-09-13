"""Natural-language chat mode: an LLM drives the Zhihu commands via tool calls."""

from __future__ import annotations

import contextlib
import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import typer

from .. import sessions
from .. import spill as spill_store
from .. import todo as todo_store
from ..compaction import (
    DEFAULT_KEEP_RECENT,
    DEFAULT_MAX_TOKENS,
    compact,
    count_messages_tokens,
    microcompact,
)
from ..composer import (
    ASK_TEMPLATE,
    BODY_TEMPLATE,
    edit_text,
    is_cancelled,
    markdown_to_html,
    split_title,
)
from ..exceptions import ZhihuError
from ..hooks import HookRegistry, load_hooks
from ..llm import LLMClient, resolve_llm_config
from ..output import console, error_console, html_to_markdown, normalize_url
from ..plugins import ToolDef, load_plugins
from ..prompt import build_prompt_sections, load_memory
from ._common import require_client
from .download import download_answer_impl, download_article_impl

MAX_TEXT = 3000
DEFAULT_MAX_INLINE_CHARS = 6000


def _clip(text: str, limit: int = MAX_TEXT) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + f"\n…（已截断，共 {len(text)} 字）"


def _tools_spec() -> list[dict[str, Any]]:
    def fn(name: str, desc: str, props: dict, required: list[str]) -> dict:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": {"type": "object", "properties": props, "required": required},
            },
        }

    return [
        fn("hot", "获取知乎热榜", {"limit": {"type": "integer", "description": "条数，默认10"}}, []),
        fn("search", "综合搜索知乎内容", {
            "query": {"type": "string"},
            "limit": {"type": "integer"},
        }, ["query"]),
        fn("question", "查看问题详情及其回答", {
            "question_id": {"type": "integer"},
            "limit": {"type": "integer", "description": "回答条数，默认5"},
        }, ["question_id"]),
        fn("answer", "查看某条回答全文", {"answer_id": {"type": "integer"}}, ["answer_id"]),
        fn("article", "查看某篇专栏文章全文", {"article_id": {"type": "integer"}}, ["article_id"]),
        fn("user", "查看用户主页及最近回答", {
            "token": {"type": "string", "description": "url_token"},
            "limit": {"type": "integer"},
        }, ["token"]),
        fn("me", "查看当前登录账号信息", {}, []),
        fn("download_answer", "把某条回答导出为 Markdown 文件", {"answer_id": {"type": "integer"}}, ["answer_id"]),
        fn("download_article", "把某篇文章导出为 Markdown 文件", {"article_id": {"type": "integer"}}, ["article_id"]),
        fn("vote", "赞同或反对回答/文章（写操作）", {
            "target": {"type": "string", "enum": ["answer", "article"]},
            "content_id": {"type": "integer"},
            "direction": {"type": "string", "enum": ["up", "down"]},
        }, ["target", "content_id"]),
        fn("collect", "收藏回答/文章到收藏夹（写操作）", {
            "content_id": {"type": "integer"},
            "content_type": {"type": "string", "enum": ["answer", "article"]},
            "collection_id": {"type": "integer"},
        }, ["content_id", "collection_id"]),
        fn("follow", "关注用户或问题（写操作）", {
            "member": {"type": "string", "description": "用户 url_token"},
            "question_id": {"type": "integer"},
        }, []),
        fn("comment", "对回答/文章发表评论（写操作）", {
            "target": {"type": "string", "enum": ["answer", "article"]},
            "content_id": {"type": "integer"},
            "content": {"type": "string"},
        }, ["target", "content_id", "content"]),
        fn("publish", "在问题下发布回答，content 为知乎 HTML（写操作）", {
            "question_id": {"type": "integer"},
            "content": {"type": "string"},
        }, ["question_id", "content"]),
        fn("feed", "获取首页推荐流", {"limit": {"type": "integer"}}, []),
        fn("topic", "查看话题详情", {"topic_id": {"type": "string"}}, ["topic_id"]),
        fn("comments", "查看回答或文章的评论", {
            "target": {"type": "string", "enum": ["answer", "article"]},
            "content_id": {"type": "integer"},
            "limit": {"type": "integer"},
        }, ["target", "content_id"]),
        fn("collections", "列出收藏夹", {"limit": {"type": "integer"}}, []),
        fn("followers", "列出粉丝", {"limit": {"type": "integer"}}, []),
        fn("notifications", "查看通知消息", {"limit": {"type": "integer"}}, []),
        fn("ask_question", "发布提问（写操作）", {
            "title": {"type": "string"},
            "detail": {"type": "string", "description": "支持 HTML"},
        }, ["title"]),
        fn("create_pin", "发布想法（写操作）", {
            "title": {"type": "string"},
            "content": {"type": "string"},
        }, ["title"]),
        fn("create_article", "发布专栏文章（写操作）", {
            "title": {"type": "string"},
            "content": {"type": "string", "description": "支持 HTML"},
        }, ["title", "content"]),
        fn("delete_content", "删除自己发布的内容（写操作）", {
            "target": {"type": "string", "enum": ["question", "pin", "article"]},
            "content_id": {"type": "integer"},
        }, ["target", "content_id"]),
        fn("uncollect", "从收藏夹移除内容（写操作）", {
            "content_id": {"type": "integer"},
            "collection_id": {"type": "integer"},
            "content_type": {"type": "string", "enum": ["answer", "article"]},
        }, ["content_id", "collection_id"]),
        fn("delete_comment", "删除自己发表的评论（写操作）", {
            "comment_id": {"type": "integer"},
        }, ["comment_id"]),
        fn("compose_publish", "打开 Markdown 编辑器（MarkText）让用户亲手撰写并发布内容。"
           "kind=answer 时需要 question_id；提问/想法/文章会自动从首行 `# 标题` 取标题。",
           {
               "kind": {"type": "string", "enum": ["question", "pin", "article", "answer"]},
               "title": {"type": "string", "description": "可选，用户未写标题时使用"},
               "question_id": {"type": "integer", "description": "kind=answer 时必填"},
           }, ["kind"]),
        fn("read_spill", "读取之前因过大而溢出的工具结果（用溢出提示里的路径），支持 offset/limit 分段", {
            "path": {"type": "string", "description": "溢出文件的 locator 路径"},
            "offset": {"type": "integer", "description": "起始字符偏移"},
            "limit": {"type": "integer", "description": "读取字符数，0 表示到结尾"},
        }, ["path"]),
        fn("todo_write", "创建或更新任务清单（多步任务时用），每次传入完整列表；status 取值 pending/in_progress/completed", {
            "todos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "任务描述"},
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed"],
                        },
                    },
                    "required": ["content", "status"],
                },
            },
        }, ["todos"]),
    ]


_WRITE_TOOLS = {
    "vote", "collect", "follow", "comment", "publish",
    "ask_question", "create_pin", "create_article", "delete_content",
    "uncollect", "delete_comment",
}

# Tools blocked while the agent is in "plan" mode (read-only planning).
_PLAN_BLOCKED = _WRITE_TOOLS | {"compose_publish"}


def _brief_result(result: Any) -> str:
    """A short human hint for the TUI, e.g. number of items returned."""
    if isinstance(result, list):
        return f"{len(result)} 条"
    if isinstance(result, dict):
        if "error" in result or result.get("declined"):
            return "失败"
        data = result.get("data")
        if isinstance(data, list):
            return f"{len(data)} 条"
    return ""


def base_system_prompt() -> str:
    """The fixed base section; plugins and memory append to it."""
    return (
        "你是「知乎 CLI」的中文助手。用户用自然语言提出需求，你通过调用工具获取知乎的真实数据，"
        "不要凭空编造。拿到工具结果后，用简洁中文总结，并附上相关链接。"
        "涉及写操作（赞同/收藏/关注/评论/发布）时，先说明你将要做什么，系统会让用户再次确认。"
        "当用户想亲自撰写内容（提问/想法/文章/回答）时，调用 compose_publish，"
        "它会打开 Markdown 编辑器让用户写；不要自己代写正文。"
        "如果信息不足（比如缺少 ID），先向用户询问。"
        "面对需要多个步骤的任务（如批量导出、逐条整理），先用 todo_write 列出计划，"
        "并在推进时更新各项状态。"
        f"当前时间：{datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M')}。"
    )


class ChatAgent:
    def __init__(
        self,
        client,
        llm: LLMClient,
        *,
        assume_yes: bool = False,
        confirm: Callable[[str, dict[str, Any]], bool] | None = None,
        compose: Callable[[str], str] | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        keep_recent: int = DEFAULT_KEEP_RECENT,
        session_id: str | None = None,
        plugin_tools: dict[str, ToolDef] | None = None,
        max_inline_chars: int = DEFAULT_MAX_INLINE_CHARS,
        memory: str = "",
        prompt_sections: list[tuple[int, str]] | None = None,
        hooks: HookRegistry | None = None,
        plan_mode: bool = False,
    ) -> None:
        self.client = client
        self.llm = llm
        self.assume_yes = assume_yes
        self._confirm_fn = confirm
        self._compose_fn = compose
        self.max_tokens = max_tokens
        self.keep_recent = keep_recent
        self.session_id = session_id or sessions.new_session_id()
        self._plugin_tools = plugin_tools or {}
        self.max_inline_chars = max_inline_chars
        self._memory = memory
        self._prompt_sections = prompt_sections or []
        self._hooks = hooks
        self.plan_mode = plan_mode
        self.tool_calls = 0
        self.compactions = 0
        self.todos: list[dict[str, str]] = []
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": self._system_prompt()}]

    def _tool_content(self, result: Any, tool_name: str, call_id: str | None) -> str:
        """Inline small tool results; spill oversized ones to a private file."""
        text = json.dumps(result, ensure_ascii=False, default=str)
        if len(text) <= self.max_inline_chars:
            return text
        ref = spill_store.save_text(self.session_id, tool_name, call_id or "", "result", text)
        return (
            f"{spill_store.preview(text)}\n"
            f"…[结果 {ref.bytes} 字节过大，已溢出到 {ref.locator}；{ref.retrieval_hint}]"
        )

    def _all_tools(self) -> list[dict[str, Any]]:
        specs = _tools_spec()
        specs.extend(tool.spec() for tool in self._plugin_tools.values())
        return specs

    def _persist(self) -> None:
        with contextlib.suppress(Exception):  # persistence must never break a turn
            sessions.save_session(self.session_id, self.messages, model=self.llm.config.model)

    def _system_prompt(self) -> str:
        prompt = build_prompt_sections(base_system_prompt(), self._memory, self._prompt_sections)
        if self.plan_mode:
            prompt += (
                "\n\n【当前模式：plan（规划）】只进行只读查询与方案规划，"
                "禁止执行任何写操作；如需执行，提示用户按 Shift+Tab 切换到 build 模式。"
            )
        else:
            prompt += "\n\n【当前模式：build（执行）】可以执行读写操作。"
        return prompt

    def _is_write_tool(self, name: str) -> bool:
        if name in _PLAN_BLOCKED:
            return True
        tool = self._plugin_tools.get(name)
        return bool(tool and tool.write)

    # -- tool implementations ---------------------------------------------

    def _hot(self, limit: int = 10) -> Any:
        data = self.client.get("/api/v3/feed/topstory/hot-lists/total", limit=limit, desktop="true")
        out = []
        for item in data.get("data", [])[:limit]:
            target = item.get("target", {})
            title = target.get("title") or target.get("titleArea", {}).get("text", "")
            if title:
                out.append({"title": title, "heat": target.get("metricsArea", {}).get("text", ""),
                            "url": normalize_url(target.get("url", ""))})
        return out

    def _search(self, query: str, limit: int = 10) -> Any:
        data = self.client.request("GET", "/api/v4/search_v3", params={
            "t": "general", "q": query, "correction": 1, "offset": 0, "limit": limit,
            "lc_idx": 0, "show_all_topics": 0, "search_hash_id": "",
            "vertical_info": "0,0,0,0,0,0,0,0,0,0",
        })
        out = []
        for item in data.get("data", []):
            obj = item.get("object", item)
            out.append({
                "type": obj.get("type"),
                "title": obj.get("title") or (obj.get("question") or {}).get("title"),
                "author": (obj.get("author") or {}).get("name"),
                "excerpt": _clip(obj.get("excerpt") or obj.get("description") or "", 200),
                "url": normalize_url(obj.get("url") or ""),
            })
        return out

    def _question(self, question_id: int, limit: int = 5) -> Any:
        q = self.client.get(f"/api/v4/questions/{question_id}")
        answers = []
        params = {"include": "data[*].content", "sort_by": "default"}
        for item in self.client.paginate(
            f"/api/v4/questions/{question_id}/answers", params, limit=20, max_items=limit
        ):
            answers.append({
                "author": (item.get("author") or {}).get("name"),
                "voteup_count": item.get("voteup_count"),
                "content": _clip(html_to_markdown(item.get("content", ""))),
            })
        return {"title": q.get("title"), "detail": _clip(html_to_markdown(q.get("detail", ""))),
                "url": normalize_url(q.get("url") or ""), "answers": answers}

    def _answer(self, answer_id: int) -> Any:
        a = self.client.get(
            f"/api/v4/answers/{answer_id}",
            include="content,excerpt,voteup_count,comment_count,created_time,author,question",
        )
        return {
            "question": (a.get("question") or {}).get("title"),
            "author": (a.get("author") or {}).get("name"),
            "voteup_count": a.get("voteup_count"),
            "url": normalize_url(a.get("url") or ""),
            "content": _clip(html_to_markdown(a.get("content", ""))),
        }

    def _article(self, article_id: int) -> Any:
        a = self.client.get(f"/api/v4/articles/{article_id}",
                            include="content,voteup_count,comment_count,created,author")
        return {
            "title": a.get("title"),
            "author": (a.get("author") or {}).get("name"),
            "voteup_count": a.get("voteup_count"),
            "url": normalize_url(a.get("url") or ""),
            "content": _clip(html_to_markdown(a.get("content", ""))),
        }

    def _user(self, token: str, limit: int = 5) -> Any:
        m = self.client.get(f"/api/v4/members/{token}",
                            include="name,url_token,headline,description,answer_count,followers_count")
        answers = []
        params = {"include": "data[*].content", "sort_by": "created"}
        for item in self.client.paginate(
            f"/api/v4/members/{token}/answers", params, limit=20, max_items=limit
        ):
            answers.append({
                "question": (item.get("question") or {}).get("title"),
                "excerpt": _clip(html_to_markdown(item.get("content", "")), 300),
            })
        return {"name": m.get("name"), "url_token": m.get("url_token"), "headline": m.get("headline"),
                "description": m.get("description"), "answer_count": m.get("answer_count"),
                "followers_count": m.get("followers_count"), "recent_answers": answers}

    def _me(self) -> Any:
        return self.client.get("/api/v4/me")

    # -- dispatch ----------------------------------------------------------

    def _read_spill(self, path: str, offset: int = 0, limit: int = 8000) -> Any:
        return {"content": spill_store.read_spill(path, offset=offset, limit=limit)}

    def _todo_write(self, todos: list[dict[str, Any]]) -> Any:
        self.todos = todo_store.normalize(todos)
        return {"todos": self.todos, "rendered": todo_store.render_plain(self.todos)}

    def _dispatch(self, name: str, args: dict[str, Any]) -> Any:
        if self.plan_mode and self._is_write_tool(name):
            return {
                "denied": True,
                "message": "当前为 plan 模式：只做只读查询与规划；按 Shift+Tab 切到 build 模式再执行写操作。",
            }
        args = dict(args or {})
        hook_asked = False
        if self._hooks is not None:
            pre = self._hooks.run_pre(name, args)
            if pre is not None:
                if pre.decision == "deny":
                    return {"denied": True, "message": pre.reason or "被钩子拒绝"}
                if pre.args is not None:
                    args = pre.args
                if pre.decision == "ask":
                    hook_asked = True
                    if not self._confirm(name, args):
                        return {"declined": True, "message": "用户取消了该操作。"}
        result = self._dispatch_inner(name, args, hook_asked)
        if self._hooks is not None:
            result = self._hooks.run_post(name, args, result)
        return result

    def _dispatch_inner(self, name: str, args: dict[str, Any], hook_asked: bool) -> Any:
        if name in self._plugin_tools:
            tool = self._plugin_tools[name]
            if tool.write and not hook_asked and not self._confirm(name, args):
                return {"declined": True, "message": "用户取消了该操作。"}
            return tool.handler(self.client, **args)
        if name in _WRITE_TOOLS and not hook_asked and not self._confirm(name, args):
            return {"declined": True, "message": "用户取消了该操作。"}
        table: dict[str, Callable[..., Any]] = {
            "hot": self._hot, "search": self._search, "question": self._question,
            "answer": self._answer, "article": self._article, "user": self._user, "me": self._me,
            "download_answer": lambda answer_id: download_answer_impl(self.client, answer_id),
            "download_article": lambda article_id: download_article_impl(self.client, article_id),
            "vote": self._vote, "collect": self._collect, "follow": self._follow,
            "comment": self._comment, "publish": self._publish,
            "feed": self._feed, "topic": self._topic, "comments": self._comments,
            "collections": self._collections, "followers": self._followers,
            "notifications": self._notifications, "ask_question": self._ask_question,
            "create_pin": self._create_pin, "create_article": self._create_article,
            "delete_content": self._delete_content,
            "uncollect": self._uncollect, "delete_comment": self._delete_comment,
            "compose_publish": self._compose_publish, "read_spill": self._read_spill,
            "todo_write": self._todo_write,
        }
        func = table.get(name)
        if func is None:
            return {"error": f"unknown tool {name}"}
        return func(**args)

    def _confirm(self, name: str, args: dict[str, Any]) -> bool:
        if self.assume_yes:
            return True
        if self._confirm_fn is not None:
            return bool(self._confirm_fn(name, args))
        console.print(f"[yellow]即将执行写操作[/yellow] {name} {json.dumps(args, ensure_ascii=False)}")
        return typer.confirm("确认？", default=False)

    def _vote(self, target: str, content_id: int, direction: str = "up") -> Any:
        kind = "answers" if target == "answer" else "articles"
        return self.client.post(f"/api/v4/{kind}/{content_id}/voters", json_body={"type": direction})

    def _collect(self, content_id: int, collection_id: int, content_type: str = "answer") -> Any:
        return self.client.post(f"/api/v4/collections/{collection_id}/contents",
                                json_body={"content_id": content_id, "content_type": content_type})

    def _follow(self, member: str | None = None, question_id: int | None = None) -> Any:
        if member:
            return self.client.post(f"/api/v4/members/{member}/followers", json_body={})
        if question_id:
            return self.client.post(f"/api/v4/questions/{question_id}/followers", json_body={})
        return {"error": "需要 member 或 question_id"}

    def _comment(self, target: str, content_id: int, content: str) -> Any:
        kind = "answers" if target == "answer" else "articles"
        return self.client.post(f"/api/v4/{kind}/{content_id}/comments",
                                json_body={"content": content, "type": "comment"})

    def _publish(self, question_id: int, content: str) -> Any:
        return self.client.post(f"/api/v4/questions/{question_id}/answers",
                                json_body={"content": content, "resume": False})

    def _feed(self, limit: int = 10) -> Any:
        data = self.client.recommend_feed(limit)
        out = []
        for item in data.get("data", [])[:limit]:
            target = item.get("target", {})
            out.append({
                "type": target.get("type"),
                "title": target.get("title") or (target.get("question") or {}).get("title"),
                "author": (target.get("author") or {}).get("name"),
                "excerpt": _clip(target.get("excerpt") or "", 150),
                "url": normalize_url(target.get("url") or ""),
            })
        return out

    def _topic(self, topic_id: str) -> Any:
        t = self.client.topic(topic_id)
        return {
            "name": t.get("name"), "introduction": _clip(t.get("introduction") or "", 300),
            "followers_count": t.get("followers_count"), "questions_count": t.get("questions_count"),
            "url": f"https://www.zhihu.com/topic/{topic_id}",
        }

    def _comments(self, target: str, content_id: int, limit: int = 10) -> Any:
        data = (self.client.article_comments(content_id, limit=limit) if target == "article"
                else self.client.answer_comments(content_id, limit=limit))
        return [
            {"author": (c.get("author") or {}).get("name"),
             "content": _clip(c.get("content") or "", 300)}
            for c in data.get("data", [])
        ]

    def _collections(self, limit: int = 10) -> Any:
        data = self.client.favlists(limit=limit)
        return [{"title": c.get("title"), "id": c.get("id"),
                 "answer_count": c.get("answer_count")} for c in data.get("data", [])]

    def _followers(self, limit: int = 10) -> Any:
        token = self.client.me().get("url_token", "")
        data = self.client.followers(token, limit=limit)
        return [{"name": f.get("name"), "url_token": f.get("url_token"),
                 "headline": f.get("headline")} for f in data.get("data", [])]

    def _notifications(self, limit: int = 10) -> Any:
        data = self.client.notifications(limit=limit)
        return [{"content": (i.get("content") or {}).get("text") or i.get("text")}
                for i in data.get("data", [])]

    def _ask_question(self, title: str, detail: str = "") -> Any:
        return self.client.create_question(title, detail)

    def _create_pin(self, title: str, content: str = "") -> Any:
        return self.client.create_pin(title, content)

    def _create_article(self, title: str, content: str) -> Any:
        return self.client.create_article(title, content)

    def _delete_content(self, target: str, content_id: int) -> Any:
        if target == "question":
            return self.client.delete_question(content_id)
        if target == "pin":
            return self.client.delete_pin(content_id)
        return self.client.delete_article(content_id)

    def _uncollect(self, content_id: int, collection_id: int,
                   content_type: str = "answer") -> Any:
        return self.client.collection_remove(collection_id, content_id, content_type)

    def _delete_comment(self, comment_id: int) -> Any:
        return self.client.delete_comment(comment_id)

    def _compose(self, template: str) -> str:
        if self._compose_fn is not None:
            return self._compose_fn(template)
        return edit_text(template)

    def _compose_publish(self, kind: str, title: str | None = None,
                         question_id: int | None = None) -> Any:
        template = ASK_TEMPLATE if kind in ("question", "pin", "article") else BODY_TEMPLATE
        markdown = self._compose(template)
        if not markdown or is_cancelled(markdown, template):
            return {"cancelled": True, "message": "用户取消了编辑。"}
        if kind == "answer":
            if not question_id:
                return {"error": "kind=answer 需要 question_id"}
            html = markdown_to_html(markdown, self.client, "answer")
            return self.client.post(
                f"/api/v4/questions/{question_id}/answers",
                json_body={"content": html, "resume": False},
            )
        file_title, body = split_title(markdown)
        final_title = (title or file_title).strip()
        html = markdown_to_html(body, self.client, kind)
        if kind == "question":
            return self.client.create_question(final_title, html)
        if kind == "pin":
            return self.client.create_pin(final_title, html)
        return self.client.create_article(final_title, html)

    # -- agent loop --------------------------------------------------------

    def _maybe_compact(self) -> dict[str, Any] | None:
        """Cheap microcompact always; full LLM summarization when over budget."""
        self.messages, _ = microcompact(self.messages)
        if count_messages_tokens(self.messages) <= self.max_tokens:
            return None
        self.messages, info = compact(self.messages, self.llm, keep_recent=self.keep_recent)
        if info.get("compacted"):
            self.compactions += 1
        return info if info.get("compacted") else None

    def force_compact(self, instructions: str | None = None) -> dict[str, Any]:
        self.messages, info = compact(
            self.messages, self.llm, keep_recent=self.keep_recent, instructions=instructions
        )
        if info.get("compacted"):
            self.compactions += 1
        return info

    def stats(self) -> dict[str, Any]:
        usage = getattr(self.llm, "usage", {}) or {}
        return {
            "requests": usage.get("requests", 0),
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "tool_calls": self.tool_calls,
            "compactions": self.compactions,
            "messages": len(self.messages),
            "context_tokens": count_messages_tokens(self.messages),
        }

    def send(self, user_input: str) -> str:
        info = self._maybe_compact()
        if info:
            console.print(
                f"[dim]已压缩上下文：{info['pre_tokens']} → {info['post_tokens']} tokens[/dim]"
            )
        self.messages.append({"role": "user", "content": user_input})
        tools = self._all_tools()
        for _ in range(8):
            message = self.llm.chat(self.messages, tools)
            self.messages.append(message)
            tool_calls = message.get("tool_calls")
            if not tool_calls:
                self._persist()
                return message.get("content", "")
            for call in tool_calls:
                self.tool_calls += 1
                fn = call.get("function", {})
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = {}
                console.print(f"[dim]→ 调用 {name}({json.dumps(args, ensure_ascii=False)})[/dim]")
                try:
                    result = self._dispatch(name, args)
                except Exception as exc:  # noqa: BLE001 - report tool errors to the model
                    result = {"error": str(exc)}
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id"),
                    "content": self._tool_content(result, name, call.get("id")),
                })
        self._persist()
        return "（工具调用次数过多，已停止）"

    def send_stream(self, user_input: str, cancel_event=None):
        """Like :meth:`send` but yields ``(kind, *payload)`` events for live UIs.

        When *cancel_event* is set mid-generation, yields ``("cancelled",)``
        and stops without appending the partial assistant message.
        """
        info = self._maybe_compact()
        if info:
            yield ("compact", info)
        self.messages.append({"role": "user", "content": user_input})
        tools = self._all_tools()
        for _ in range(8):
            if cancel_event is not None and cancel_event.is_set():
                yield ("cancelled",)
                return
            final_message: dict[str, Any] | None = None
            for event in self.llm.chat_stream(self.messages, tools, cancel_event=cancel_event):
                if event["type"] == "cancelled":
                    yield ("cancelled",)
                    return
                elif event["type"] == "delta":
                    yield ("delta", event["text"])
                elif event["type"] == "done":
                    final_message = event["message"]
            if final_message is None:
                yield ("done", "")
                return
            self.messages.append(final_message)
            tool_calls = final_message.get("tool_calls")
            if not tool_calls:
                self._persist()
                yield ("done", final_message.get("content") or "")
                return
            for call in tool_calls:
                if cancel_event is not None and cancel_event.is_set():
                    yield ("cancelled",)
                    return
                self.tool_calls += 1
                function = call.get("function", {})
                name = function.get("name", "")
                try:
                    args = json.loads(function.get("arguments") or "{}")
                except ValueError:
                    args = {}
                yield ("tool", name, json.dumps(args, ensure_ascii=False))
                try:
                    result = self._dispatch(name, args)
                except Exception as exc:  # noqa: BLE001 - surface tool errors to the model
                    result = {"error": str(exc)}
                yield ("tool_done", name, _brief_result(result))
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id"),
                    "content": self._tool_content(result, name, call.get("id")),
                })
        self._persist()
        yield ("done", "（工具调用次数过多，已停止）")


def _make_agent(ctx: typer.Context, api_key, base_url, model, assume_yes: bool) -> ChatAgent:
    config = resolve_llm_config(api_key, base_url, model)
    client = require_client(ctx)
    llm = LLMClient(config)
    plugins = load_plugins()
    return ChatAgent(
        client,
        llm,
        assume_yes=assume_yes,
        plugin_tools=plugins.tools,
        memory=load_memory(),
        prompt_sections=plugins.prompts,
        hooks=load_hooks(plugins.hooks),
    )


def _restore_agent(agent: ChatAgent, resume: bool, session_id: str | None) -> None:
    if not resume and not session_id:
        return
    try:
        sid, messages = sessions.load_session(session_id)
    except ZhihuError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        return
    if messages:
        agent.messages = [agent.messages[0]] + list(messages[1:])
        agent.session_id = sid
        console.print(f"[dim]已恢复会话 {sid}（{len(messages) - 1} 条历史）[/dim]")


def chat(
    ctx: typer.Context,
    api_key: str = typer.Option(None, "--api-key", help="模型 API Key"),
    base_url: str = typer.Option(None, "--base-url", help="OpenAI 兼容接口地址"),
    model: str = typer.Option(None, "--model", help="模型名"),
    yes: bool = typer.Option(False, "--yes", "-y", help="写操作不再逐次确认"),
    resume: bool = typer.Option(False, "--continue", "-c", help="恢复最近一次会话"),
    session_id: str = typer.Option(None, "--session", help="恢复指定会话 ID"),
) -> None:
    """进入自然语言对话模式（输入 exit 退出）。"""
    agent = _make_agent(ctx, api_key, base_url, model, yes)
    _restore_agent(agent, resume, session_id)
    console.print(
        "[bold cyan]知乎对话模式[/bold cyan] 用中文描述，输入 [bold]/compact[/bold] 压缩上下文，"
        f"[bold]exit[/bold] 退出。会话 [dim]{agent.session_id}[/dim]"
    )
    try:
        while True:
            try:
                text = input("你 > ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print()
                break
            if text in {"exit", "quit", "退出", "q"}:
                break
            if not text:
                continue
            if text == "/compact":
                info = agent.force_compact()
                if info.get("compacted"):
                    console.print(
                        f"[dim]已压缩上下文：{info['pre_tokens']} → {info['post_tokens']} tokens"
                        f"（合并 {info['summarized']} 条）[/dim]"
                    )
                else:
                    console.print(f"无需压缩（{info.get('reason', '')}）。")
                continue
            if text == "/stats":
                stats = agent.stats()
                console.print(
                    f"[dim]请求 {stats['requests']} · 输入 {stats['prompt_tokens']} · "
                    f"输出 {stats['completion_tokens']} · 合计 {stats['total_tokens']} tokens · "
                    f"工具 {stats['tool_calls']} · 压缩 {stats['compactions']} · "
                    f"上下文 ~{stats['context_tokens']} tokens[/dim]"
                )
                continue
            if text == "/todos":
                if agent.todos:
                    console.print("任务清单：\n" + todo_store.render_plain(agent.todos))
                else:
                    console.print("当前无任务清单。")
                continue
            if text == "/connect":
                console.print("模型配置请在终端运行：zhihu connect（--list 查看内置供应商）")
                continue
            if text == "/copy":
                console.print("复制请在 TUI 中操作：Ctrl+C 复制选区，/copy 复制上一条回答。")
                continue
            try:
                reply = agent.send(text)
            except KeyboardInterrupt:
                # Ctrl+C during an in-flight LLM call cancels just this turn
                # (the connection is closed as the request unwinds).
                console.print("[yellow]（已取消本次生成，会话保留）[/yellow]")
                continue
            except Exception as exc:  # noqa: BLE001 - keep the REPL alive
                error_console.print(f"出错：{exc}")
                continue
            console.print("[bold green]知乎 >[/bold green]")
            console.print(reply)
    finally:
        agent.client.close()
        agent.llm.close()


def ask(
    ctx: typer.Context,
    prompt: list[str] = typer.Argument(..., help="要问的话"),
    api_key: str = typer.Option(None, "--api-key", help="模型 API Key"),
    base_url: str = typer.Option(None, "--base-url", help="OpenAI 兼容接口地址"),
    model: str = typer.Option(None, "--model", help="模型名"),
    yes: bool = typer.Option(False, "--yes", "-y", help="写操作不再逐次确认"),
) -> None:
    """单次自然语言提问，例如 `zhihu ask 帮我看看今天热榜`。"""
    agent = _make_agent(ctx, api_key, base_url, model, yes)
    try:
        reply = agent.send(" ".join(prompt))
        console.print(reply)
    finally:
        agent.client.close()
        agent.llm.close()


def run_tui(
    ctx: typer.Context,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    yes: bool = False,
    resume: bool = False,
    session_id: str | None = None,
) -> None:
    """Launch the full-screen TUI (also the default when running bare `zhihu`)."""
    try:
        from ..tui import ChatTUI
    except ImportError as exc:
        error_console.print("需要 textual：uv pip install textual")
        raise typer.Exit(code=1) from exc

    config = resolve_llm_config(api_key, base_url, model)
    client = require_client(ctx)
    try:
        user = client.get("/api/v4/me").get("name", "")
    except ZhihuError:
        user = ""
    llm = LLMClient(config)
    plugins = load_plugins()
    agent = ChatAgent(
        client,
        llm,
        assume_yes=yes,
        plugin_tools=plugins.tools,
        memory=load_memory(),
        prompt_sections=plugins.prompts,
        hooks=load_hooks(plugins.hooks),
    )
    _restore_agent(agent, resume, session_id)
    app = ChatTUI(agent, subtitle=config.model, user=user)
    try:
        app.run()
    finally:
        agent.client.close()
        agent.llm.close()


def tui(
    ctx: typer.Context,
    api_key: str = typer.Option(None, "--api-key", help="模型 API Key"),
    base_url: str = typer.Option(None, "--base-url", help="OpenAI 兼容接口地址"),
    model: str = typer.Option(None, "--model", help="模型名"),
    yes: bool = typer.Option(False, "--yes", "-y", help="写操作不再逐次确认"),
    resume: bool = typer.Option(False, "--continue", "-c", help="恢复最近一次会话"),
    session_id: str = typer.Option(None, "--session", help="恢复指定会话 ID"),
) -> None:
    """启动全屏 TUI 对话界面（类似 Claude Code）。"""
    run_tui(ctx, api_key, base_url, model, yes, resume, session_id)
