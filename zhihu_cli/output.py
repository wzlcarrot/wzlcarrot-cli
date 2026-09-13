"""Terminal rendering helpers built on rich."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import datetime, timezone

from markdownify import markdownify as html_to_markdown_impl
from rich.console import Console
from rich.markdown import Markdown as RichMarkdown
from rich.panel import Panel
from rich.table import Table

console = Console()
error_console = Console(stderr=True, style="bold red")


def print_json(data: object) -> None:
    console.print_json(json.dumps(data, ensure_ascii=False, default=str))


def _dt(ts: int | None) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def html_to_markdown(html: str) -> str:
    if not html:
        return ""
    text = html_to_markdown_impl(html, heading_style="ATX")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _excerpt(text: str, width: int = 100) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= width else text[: width - 1] + "…"


def normalize_url(url: str) -> str:
    """Rewrite API URLs (api.zhihu.com/questions/...) to public web URLs."""
    if not url:
        return ""
    url = url.replace("https://api.zhihu.com", "https://www.zhihu.com")
    replacements = (
        ("https://www.zhihu.com/questions/", "https://www.zhihu.com/question/"),
        ("https://www.zhihu.com/answers/", "https://www.zhihu.com/answer/"),
        ("https://www.zhihu.com/articles/", "https://zhuanlan.zhihu.com/p/"),
    )
    for old, new in replacements:
        if url.startswith(old):
            return new + url[len(old):]
    return url


def render_hot(items: Iterable[dict]) -> None:
    table = Table(title="知乎热榜", show_lines=False, header_style="bold cyan")
    table.add_column("#", justify="right", style="dim", width=4)
    table.add_column("标题", overflow="fold")
    table.add_column("热度", justify="right", style="yellow")
    table.add_column("链接", style="blue", overflow="fold")
    count = 0
    for item in items:
        target = item.get("target", {}) if isinstance(item, dict) else {}
        title = target.get("title") or target.get("titleArea", {}).get("text") or ""
        url = normalize_url(target.get("url", ""))
        heat = target.get("metricsArea", {}).get("text", "")
        if not title:
            continue
        count += 1
        table.add_row(str(count), title, str(heat), url)
    console.print(table)


def render_question(question: dict) -> None:
    title = question.get("title", "")
    detail = html_to_markdown(question.get("detail", ""))
    meta = (
        f"关注 {question.get('follower_count', 0)} · "
        f"回答 {question.get('answer_count', 0)} · "
        f"浏览 {question.get('visit_count', 0)}"
    )
    console.print(Panel(f"[bold]{title}[/bold]\n[dim]{meta}[/dim]\n{normalize_url(question.get('url', ''))}",
                        title="问题", border_style="cyan"))
    if detail:
        console.print(RichMarkdown(detail))


def render_answer(answer: dict, *, show_content: bool = True) -> None:
    author = answer.get("author", {}) or {}
    qinfo = answer.get("question", {}) or {}
    header = (
        f"[bold]{author.get('name', '匿名用户')}[/bold] "
        f"[dim]{author.get('headline', '')}[/dim]\n"
        f"赞同 {answer.get('voteup_count', 0)} · 评论 {answer.get('comment_count', 0)} · "
        f"{_dt(answer.get('created_time'))}\n{normalize_url(answer.get('url', ''))}"
    )
    title = qinfo.get("title") or answer.get("question_title") or f"回答 {answer.get('id')}"
    console.print(Panel(header, title=title, border_style="green"))
    if show_content:
        content = html_to_markdown(answer.get("content", ""))
        if content:
            console.print(RichMarkdown(content))


def render_article(article: dict) -> None:
    author = article.get("author", {}) or {}
    header = (
        f"[bold]{article.get('title', '')}[/bold]\n"
        f"[dim]{author.get('name', '')}[/dim]\n"
        f"赞同 {article.get('voteup_count', 0)} · 评论 {article.get('comment_count', 0)} · "
        f"{_dt(article.get('created'))}\n{normalize_url(article.get('url', ''))}"
    )
    console.print(Panel(header, title="文章", border_style="magenta"))
    content = html_to_markdown(article.get("content", ""))
    if content:
        console.print(RichMarkdown(content))


def render_member(member: dict) -> None:
    lines = [
        f"[bold]{member.get('name', '')}[/bold]  [dim]@{member.get('url_token', '')}[/dim]",
        member.get("headline", ""),
        member.get("description", ""),
        "",
        (
            f"回答 {member.get('answer_count', 0)} · 文章 {member.get('articles_count', 0)} · "
            f"关注者 {member.get('followers_count', 0)} · 关注 {member.get('following_count', 0)}"
        ),
        f"https://www.zhihu.com/people/{member.get('url_token', '')}",
    ]
    console.print(Panel("\n".join(x for x in lines if x is not None), title="用户", border_style="blue"))


def render_feed(items: Iterable[dict]) -> None:
    table = Table(title="推荐", header_style="bold cyan")
    table.add_column("类型", width=6, style="magenta")
    table.add_column("标题", overflow="fold")
    table.add_column("作者", width=16, style="green")
    table.add_column("链接", style="blue", overflow="fold")
    for item in items:
        target = item.get("target", item) if isinstance(item, dict) else {}
        kind = target.get("type", "?")
        title = target.get("title") or (target.get("question") or {}).get("title") or ""
        excerpt = _excerpt(target.get("excerpt") or "")
        author = (target.get("author") or {}).get("name", "")
        table.add_row(str(kind), f"{title}\n[dim]{excerpt}[/dim]", author,
                      normalize_url(target.get("url", "")))
    console.print(table)


def render_search(items: Iterable[dict]) -> None:
    table = Table(title="搜索结果", header_style="bold cyan")
    table.add_column("类型", width=6, style="magenta")
    table.add_column("标题 / 摘要", overflow="fold")
    table.add_column("作者", width=16, style="green")
    table.add_column("链接", style="blue", overflow="fold")
    for item in items:
        obj = item.get("object", item) if isinstance(item, dict) else {}
        kind = obj.get("type", item.get("type", "?")) if isinstance(obj, dict) else "?"
        title = obj.get("title") or obj.get("question", {}).get("title") or obj.get("name") or ""
        excerpt = _excerpt(obj.get("excerpt") or obj.get("description") or "")
        author = (obj.get("author") or {}).get("name", "")
        url = normalize_url(obj.get("url", ""))
        table.add_row(str(kind), f"{title}\n[dim]{excerpt}[/dim]", author, url)
    console.print(table)
