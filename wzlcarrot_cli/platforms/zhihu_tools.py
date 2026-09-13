"""Zhihu platform tools (read + write), shared by the agent and the MCP server.

Handlers are bound methods here; :func:`build_tools` returns :class:`Tool`
objects that only need a :class:`~wzlcarrot_cli.client.ZhihuClient`.
"""

from __future__ import annotations

from typing import Any

from ..client import ZhihuClient
from ..commands.download import download_answer_impl, download_article_impl
from ..output import html_to_markdown, normalize_url
from ..tools import Tool

MAX_TEXT = 3000


def _clip(text: str, limit: int = MAX_TEXT) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + f"\n…（已截断，共 {len(text)} 字）"


class ZhihuToolbox:
    def __init__(self, client: ZhihuClient) -> None:
        self.client = client

    # -- read --------------------------------------------------------------

    def hot(self, limit: int = 10) -> Any:
        data = self.client.hot_list(limit)
        out = []
        for item in data.get("data", [])[:limit]:
            target = item.get("target", {})
            title = target.get("title") or target.get("titleArea", {}).get("text", "")
            if title:
                out.append({
                    "title": title,
                    "heat": target.get("metricsArea", {}).get("text", ""),
                    "url": normalize_url(target.get("url", "")),
                })
        return out

    def search(self, query: str, limit: int = 10) -> Any:
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

    def question(self, question_id: int, limit: int = 5) -> Any:
        question = self.client.get(f"/api/v4/questions/{question_id}")
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
        return {
            "title": question.get("title"),
            "detail": _clip(html_to_markdown(question.get("detail", ""))),
            "url": normalize_url(question.get("url") or ""),
            "answers": answers,
        }

    def answer(self, answer_id: int) -> Any:
        data = self.client.get(
            f"/api/v4/answers/{answer_id}",
            include="content,voteup_count,comment_count,created_time,author,question",
        )
        return {
            "question": (data.get("question") or {}).get("title"),
            "author": (data.get("author") or {}).get("name"),
            "voteup_count": data.get("voteup_count"),
            "url": normalize_url(data.get("url") or ""),
            "content": _clip(html_to_markdown(data.get("content", ""))),
        }

    def article(self, article_id: int) -> Any:
        data = self.client.get(
            f"/api/v4/articles/{article_id}",
            include="content,voteup_count,comment_count,created,author",
        )
        return {
            "title": data.get("title"),
            "author": (data.get("author") or {}).get("name"),
            "voteup_count": data.get("voteup_count"),
            "url": normalize_url(data.get("url") or ""),
            "content": _clip(html_to_markdown(data.get("content", ""))),
        }

    def user(self, token: str, limit: int = 5) -> Any:
        data = self.client.get(
            f"/api/v4/members/{token}",
            include="name,url_token,headline,description,answer_count,followers_count",
        )
        answers = []
        params = {"include": "data[*].content", "sort_by": "created"}
        for item in self.client.paginate(
            f"/api/v4/members/{token}/answers", params, limit=20, max_items=limit
        ):
            answers.append({
                "question": (item.get("question") or {}).get("title"),
                "excerpt": _clip(html_to_markdown(item.get("content", "")), 300),
            })
        return {
            "name": data.get("name"), "url_token": data.get("url_token"),
            "headline": data.get("headline"), "description": data.get("description"),
            "answer_count": data.get("answer_count"), "followers_count": data.get("followers_count"),
            "recent_answers": answers,
        }

    def me(self) -> Any:
        return self.client.get("/api/v4/me")

    def feed(self, limit: int = 10) -> Any:
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

    def topic(self, topic_id: str) -> Any:
        data = self.client.topic(topic_id)
        return {
            "name": data.get("name"), "introduction": _clip(data.get("introduction") or "", 300),
            "followers_count": data.get("followers_count"),
            "questions_count": data.get("questions_count"),
            "url": f"https://www.zhihu.com/topic/{topic_id}",
        }

    def comments(self, target: str, content_id: int, limit: int = 10) -> Any:
        data = (self.client.article_comments(content_id, limit=limit) if target == "article"
                else self.client.answer_comments(content_id, limit=limit))
        return [
            {"author": (c.get("author") or {}).get("name"),
             "content": _clip(c.get("content") or "", 300)}
            for c in data.get("data", [])
        ]

    def collections(self, limit: int = 10) -> Any:
        data = self.client.favlists(limit=limit)
        return [{"title": c.get("title"), "id": c.get("id"),
                 "answer_count": c.get("answer_count")} for c in data.get("data", [])]

    def followers(self, limit: int = 10) -> Any:
        token = self.client.me().get("url_token", "")
        data = self.client.followers(token, limit=limit)
        return [{"name": f.get("name"), "url_token": f.get("url_token"),
                 "headline": f.get("headline")} for f in data.get("data", [])]

    def notifications(self, limit: int = 10) -> Any:
        data = self.client.notifications(limit=limit)
        return [{"content": (i.get("content") or {}).get("text") or i.get("text")}
                for i in data.get("data", [])]

    def download_answer(self, answer_id: int) -> Any:
        return {"path": str(download_answer_impl(self.client, answer_id))}

    def download_article(self, article_id: int) -> Any:
        return {"path": str(download_article_impl(self.client, article_id))}

    # -- write -------------------------------------------------------------

    def vote(self, target: str, content_id: int, direction: str = "up") -> Any:
        kind = "answers" if target == "answer" else "articles"
        return self.client.post(f"/api/v4/{kind}/{content_id}/voters", json_body={"type": direction})

    def collect(self, content_id: int, collection_id: int, content_type: str = "answer") -> Any:
        return self.client.collection_add(collection_id, content_id, content_type)

    def follow(self, member: str | None = None, question_id: int | None = None) -> Any:
        if member:
            return self.client.post(f"/api/v4/members/{member}/followers", json_body={})
        if question_id:
            return self.client.post(f"/api/v4/questions/{question_id}/followers", json_body={})
        return {"error": "需要 member 或 question_id"}

    def comment(self, target: str, content_id: int, content: str) -> Any:
        kind = "answers" if target == "answer" else "articles"
        return self.client.post(f"/api/v4/{kind}/{content_id}/comments",
                                json_body={"content": content, "type": "comment"})

    def publish(self, question_id: int, content: str) -> Any:
        return self.client.post(f"/api/v4/questions/{question_id}/answers",
                                json_body={"content": content, "resume": False})

    def ask_question(self, title: str, detail: str = "") -> Any:
        return self.client.create_question(title, detail)

    def create_pin(self, title: str, content: str = "") -> Any:
        return self.client.create_pin(title, content)

    def create_article(self, title: str, content: str) -> Any:
        return self.client.create_article(title, content)

    def delete_content(self, target: str, content_id: int) -> Any:
        if target == "question":
            return self.client.delete_question(content_id)
        if target == "pin":
            return self.client.delete_pin(content_id)
        return self.client.delete_article(content_id)

    def uncollect(self, content_id: int, collection_id: int, content_type: str = "answer") -> Any:
        return self.client.collection_remove(collection_id, content_id, content_type)

    def delete_comment(self, comment_id: int) -> Any:
        return self.client.delete_comment(comment_id)


def build_tools(client: ZhihuClient) -> list[Tool]:
    box = ZhihuToolbox(client)

    def t(name: str, desc: str, params: dict, handler, *, write: bool = False) -> Tool:
        return Tool(name, desc, params, handler, write=write)

    return [
        t("hot", "获取知乎热榜", {
            "type": "object", "properties": {"limit": {"type": "integer", "description": "条数，默认10"}},
        }, box.hot),
        t("search", "综合搜索知乎内容", {
            "type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
            "required": ["query"],
        }, box.search),
        t("question", "查看问题详情及其回答", {
            "type": "object", "properties": {"question_id": {"type": "integer"},
                                             "limit": {"type": "integer", "description": "回答条数，默认5"}},
            "required": ["question_id"],
        }, box.question),
        t("answer", "查看某条回答全文", {
            "type": "object", "properties": {"answer_id": {"type": "integer"}}, "required": ["answer_id"],
        }, box.answer),
        t("article", "查看某篇专栏文章全文", {
            "type": "object", "properties": {"article_id": {"type": "integer"}}, "required": ["article_id"],
        }, box.article),
        t("user", "查看用户主页及最近回答", {
            "type": "object", "properties": {"token": {"type": "string", "description": "url_token"},
                                             "limit": {"type": "integer"}},
            "required": ["token"],
        }, box.user),
        t("me", "查看当前登录账号信息", {"type": "object", "properties": {}}, box.me),
        t("download_answer", "把某条回答导出为 Markdown 文件", {
            "type": "object", "properties": {"answer_id": {"type": "integer"}}, "required": ["answer_id"],
        }, box.download_answer),
        t("download_article", "把某篇文章导出为 Markdown 文件", {
            "type": "object", "properties": {"article_id": {"type": "integer"}}, "required": ["article_id"],
        }, box.download_article),
        t("feed", "获取首页推荐流", {"type": "object", "properties": {"limit": {"type": "integer"}}}, box.feed),
        t("topic", "查看话题详情", {
            "type": "object", "properties": {"topic_id": {"type": "string"}}, "required": ["topic_id"],
        }, box.topic),
        t("comments", "查看回答或文章的评论", {
            "type": "object", "properties": {"target": {"type": "string", "enum": ["answer", "article"]},
                                             "content_id": {"type": "integer"}, "limit": {"type": "integer"}},
            "required": ["target", "content_id"],
        }, box.comments),
        t("collections", "列出收藏夹", {"type": "object", "properties": {"limit": {"type": "integer"}}},
          box.collections),
        t("followers", "列出粉丝", {"type": "object", "properties": {"limit": {"type": "integer"}}},
          box.followers),
        t("notifications", "查看通知消息", {"type": "object", "properties": {"limit": {"type": "integer"}}},
          box.notifications),
        t("vote", "赞同或反对回答/文章（写操作）", {
            "type": "object", "properties": {"target": {"type": "string", "enum": ["answer", "article"]},
                                             "content_id": {"type": "integer"},
                                             "direction": {"type": "string", "enum": ["up", "down"]}},
            "required": ["target", "content_id"],
        }, box.vote, write=True),
        t("collect", "收藏回答/文章到收藏夹（写操作）", {
            "type": "object", "properties": {"content_id": {"type": "integer"},
                                             "content_type": {"type": "string", "enum": ["answer", "article"]},
                                             "collection_id": {"type": "integer"}},
            "required": ["content_id", "collection_id"],
        }, box.collect, write=True),
        t("follow", "关注用户或问题（写操作）", {
            "type": "object", "properties": {"member": {"type": "string", "description": "用户 url_token"},
                                             "question_id": {"type": "integer"}},
        }, box.follow, write=True),
        t("comment", "对回答/文章发表评论（写操作）", {
            "type": "object", "properties": {"target": {"type": "string", "enum": ["answer", "article"]},
                                             "content_id": {"type": "integer"}, "content": {"type": "string"}},
            "required": ["target", "content_id", "content"],
        }, box.comment, write=True),
        t("publish", "在问题下发布回答，content 为知乎 HTML（写操作）", {
            "type": "object", "properties": {"question_id": {"type": "integer"}, "content": {"type": "string"}},
            "required": ["question_id", "content"],
        }, box.publish, write=True),
        t("ask_question", "发布提问（写操作）", {
            "type": "object", "properties": {"title": {"type": "string"},
                                             "detail": {"type": "string", "description": "支持 HTML"}},
            "required": ["title"],
        }, box.ask_question, write=True),
        t("create_pin", "发布想法（写操作）", {
            "type": "object", "properties": {"title": {"type": "string"}, "content": {"type": "string"}},
            "required": ["title"],
        }, box.create_pin, write=True),
        t("create_article", "发布专栏文章（写操作）", {
            "type": "object", "properties": {"title": {"type": "string"},
                                             "content": {"type": "string", "description": "支持 HTML"}},
            "required": ["title", "content"],
        }, box.create_article, write=True),
        t("delete_content", "删除自己发布的内容（写操作）", {
            "type": "object", "properties": {"target": {"type": "string", "enum": ["question", "pin", "article"]},
                                             "content_id": {"type": "integer"}},
            "required": ["target", "content_id"],
        }, box.delete_content, write=True),
        t("uncollect", "从收藏夹移除内容（写操作）", {
            "type": "object", "properties": {"content_id": {"type": "integer"},
                                             "collection_id": {"type": "integer"},
                                             "content_type": {"type": "string", "enum": ["answer", "article"]}},
            "required": ["content_id", "collection_id"],
        }, box.uncollect, write=True),
        t("delete_comment", "删除自己发表的评论（写操作）", {
            "type": "object", "properties": {"comment_id": {"type": "integer"}}, "required": ["comment_id"],
        }, box.delete_comment, write=True),
    ]
