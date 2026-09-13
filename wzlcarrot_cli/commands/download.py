"""Export answers / articles / questions to Markdown (optionally with images)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import typer

from ..config import default_download_dir
from ..exceptions import ZhihuError
from ..imagestore import localize_images
from ..license import is_pro
from ..output import console, html_to_markdown, normalize_url
from ._common import require_client

download_app = typer.Typer(help="导出知乎内容为 Markdown")

_ANSWER_INCLUDE = "content,excerpt,voteup_count,comment_count,created_time,updated_time,author,question"
_ARTICLE_INCLUDE = "content,voteup_count,comment_count,created,updated,author"

_IMAGES_OPTION = typer.Option(
    False, "--images", "-i", help="下载图片到本地并改写为相对路径（归档自包含）"
)


def _safe_name(text: str, fallback: str) -> str:
    text = re.sub(r"[\\/:*?\"<>|\n\r\t]+", "_", text or "").strip(" ._")
    return text[:80] or fallback


def _front_matter(meta: dict) -> str:
    lines = ["---"]
    for key, value in meta.items():
        if value is None or value == "":
            continue
        lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def _write(output_dir: Path, filename: str, meta: dict, body: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_text(f"{_front_matter(meta)}\n\n{body}\n", encoding="utf-8")
    return path


def _localize(html: str, out: Path, stem: str, images: bool) -> str:
    if not images:
        return html
    html, _ = localize_images(html, out / f"{stem}_files", f"{stem}_files")
    return html


@download_app.command("answer")
def download_answer(
    ctx: typer.Context,
    answer_id: int = typer.Argument(..., help="回答 ID"),
    output_dir: Path = typer.Option(None, "--output", "-o", help="输出目录"),
    comments: bool = typer.Option(False, "--comments", help="附带评论"),
    images: bool = _IMAGES_OPTION,
) -> None:
    """导出单条回答。"""
    client = require_client(ctx)
    with client:
        path = download_answer_impl(client, answer_id, output_dir, comments, images)
    console.print(f"[green]已导出[/green] {path}")


def download_answer_impl(
    client,
    answer_id: int,
    output_dir: Path | None = None,
    comments: bool = False,
    images: bool = False,
) -> Path:
    out = output_dir or default_download_dir()
    data = client.get(f"/api/v4/answers/{answer_id}", include=_ANSWER_INCLUDE)
    author = (data.get("author") or {}).get("name", "")
    title = (data.get("question") or {}).get("title") or f"answer-{answer_id}"
    stem = f"{_safe_name(title, 'answer')}-{answer_id}"
    body = html_to_markdown(_localize(data.get("content", ""), out, stem, images))
    if comments:
        body += _render_comments(client, f"/api/v4/answers/{answer_id}/comments")
    meta = {
        "title": f"{title} - {author}的回答",
        "author": author,
        "url": normalize_url(data.get("url", "")),
        "type": "answer",
        "voteup_count": data.get("voteup_count", 0),
        "created": data.get("created_time", 0),
    }
    return _write(out, f"{stem}.md", meta, body)


@download_app.command("article")
def download_article(
    ctx: typer.Context,
    article_id: int = typer.Argument(..., help="文章 ID"),
    output_dir: Path = typer.Option(None, "--output", "-o", help="输出目录"),
    comments: bool = typer.Option(False, "--comments", help="附带评论"),
    images: bool = _IMAGES_OPTION,
) -> None:
    """导出单篇专栏文章。"""
    client = require_client(ctx)
    with client:
        path = download_article_impl(client, article_id, output_dir, comments, images)
    console.print(f"[green]已导出[/green] {path}")


def download_article_impl(
    client,
    article_id: int,
    output_dir: Path | None = None,
    comments: bool = False,
    images: bool = False,
) -> Path:
    out = output_dir or default_download_dir()
    data = client.get(f"/api/v4/articles/{article_id}", include=_ARTICLE_INCLUDE)
    title = data.get("title") or f"article-{article_id}"
    stem = f"{_safe_name(title, 'article')}-{article_id}"
    body = html_to_markdown(_localize(data.get("content", ""), out, stem, images))
    if comments:
        body += _render_comments(client, f"/api/v4/articles/{article_id}/comments")
    meta = {
        "title": title,
        "author": (data.get("author") or {}).get("name", ""),
        "url": normalize_url(data.get("url", "")),
        "type": "article",
        "voteup_count": data.get("voteup_count", 0),
        "created": data.get("created", 0),
    }
    return _write(out, f"{stem}.md", meta, body)


@download_app.command("question")
def download_question(
    ctx: typer.Context,
    question_id: int = typer.Argument(..., help="问题 ID"),
    output_dir: Path = typer.Option(None, "--output", "-o", help="输出目录"),
    limit: int = typer.Option(10, "--limit", "-n", min=1, max=50, help="导出回答数"),
    images: bool = _IMAGES_OPTION,
) -> None:
    """导出问题及其回答。"""
    client = require_client(ctx)
    out = output_dir or default_download_dir()
    with client:
        question = client.get(f"/api/v4/questions/{question_id}")
        title = question.get("title") or f"question-{question_id}"
        stem = f"{_safe_name(title, 'question')}-{question_id}"
        parts = [html_to_markdown(_localize(question.get("detail", ""), out, stem, images))]
        params = {"include": "data[*].content", "sort_by": "default"}
        for item in client.paginate(
            f"/api/v4/questions/{question_id}/answers", params, limit=20, max_items=limit
        ):
            author = (item.get("author") or {}).get("name", "匿名用户")
            content = html_to_markdown(_localize(item.get("content", ""), out, stem, images))
            parts.append(f"## {author}（赞同 {item.get('voteup_count', 0)}）\n\n{content}")
        body = "\n\n---\n\n".join(p for p in parts if p)
    meta = {
        "title": title,
        "url": normalize_url(question.get("url", "")),
        "type": "question",
        "answer_count": question.get("answer_count", 0),
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }
    path = _write(out, f"{stem}.md", meta, body)
    console.print(f"[green]已导出[/green] {path}")


def _render_comments(client, path: str, limit: int = 20) -> str:
    try:
        data = client.request("GET", path, params={"order": "normal", "offset": 0, "limit": limit})
    except ZhihuError:
        return ""
    lines = ["", "## 评论", ""]
    for item in data.get("data", []):
        author = (item.get("author") or {}).get("name", "")
        content = html_to_markdown(item.get("content", ""))
        lines.append(f"- **{author}**：{content}")
    return "\n".join(lines)


@download_app.command("collection")
def download_collection(
    ctx: typer.Context,
    collection_id: int = typer.Argument(..., help="收藏夹 ID"),
    output_dir: Path = typer.Option(None, "--output", "-o", help="输出目录"),
    images: bool = _IMAGES_OPTION,
    limit: int = typer.Option(0, "--limit", "-n", min=0, help="导出条数，0 = 全部（Pro）"),
) -> None:
    """导出收藏夹全部内容（免费版最多 5 条，Pro 不限）。"""
    client = require_client(ctx)
    out = output_dir or default_download_dir()
    pro = is_pro()
    free_cap = 5
    exported = 0
    with client:
        params: dict = {}
        for item in client.paginate(
            f"/api/v4/collections/{collection_id}/contents", params, limit=20
        ):
            if limit and exported >= limit:
                break
            if not pro and exported >= free_cap:
                console.print(
                    "[yellow]免费版最多导出 5 条；激活 Pro 解锁全部："
                    "wzlcarrot license activate <key>[/yellow]"
                )
                break
            content = item.get("content") or {}
            content_id = content.get("id")
            content_type = content.get("type")
            if not content_id:
                continue
            if content_type == "answer":
                download_answer_impl(client, int(content_id), out, False, images)
            elif content_type == "article":
                download_article_impl(client, int(content_id), out, False, images)
            else:
                continue
            exported += 1
    console.print(f"[green]已导出 {exported} 条[/green]")
