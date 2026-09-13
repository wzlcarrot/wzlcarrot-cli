"""Question / answer / article commands."""

from __future__ import annotations

import typer

from ..output import console, render_answer, render_article, render_question
from ._common import emit, require_client

_ANSWER_INCLUDE = "content,excerpt,voteup_count,comment_count,created_time,updated_time,author,question"
_ARTICLE_INCLUDE = "content,voteup_count,comment_count,created,updated,author"


def _print_comments(ctx: typer.Context, client, path: str, limit: int) -> None:
    data = client.get(path, offset=0, limit=limit, order="normal", status="open")
    if emit(ctx, data):
        return
    console.print("\n[bold]评论[/bold]")
    for item in data.get("data", []):
        author = (item.get("author") or {}).get("name", "")
        content = item.get("content", "")
        console.print(f"  [green]{author}[/green]：{content}")


def question(
    ctx: typer.Context,
    question_id: int = typer.Argument(..., help="问题 ID"),
    show_answers: bool = typer.Option(False, "--answers", "-a", help="一并列出回答"),
    limit: int = typer.Option(10, "--limit", "-n", min=1, max=50, help="列出回答条数"),
    sort_by: str = typer.Option("default", "--sort", help="default / created / updated"),
) -> None:
    """查看问题详情（可选回答列表）。"""
    client = require_client(ctx)
    with client:
        data = client.get(f"/api/v4/questions/{question_id}")
        if emit(ctx, data):
            return
        render_question(data)
        if show_answers:
            params = {"include": "data[*].content", "sort_by": sort_by}
            for item in client.paginate(
                f"/api/v4/questions/{question_id}/answers", params, limit=20, max_items=limit
            ):
                render_answer(item)


def answer(
    ctx: typer.Context,
    answer_id: int = typer.Argument(..., help="回答 ID"),
    comments: bool = typer.Option(False, "--comments", "-c", help="附带评论"),
    limit: int = typer.Option(20, "--limit", "-n", min=1, max=100, help="评论条数"),
) -> None:
    """查看回答全文。"""
    client = require_client(ctx)
    with client:
        data = client.get(f"/api/v4/answers/{answer_id}", include=_ANSWER_INCLUDE)
        if emit(ctx, data):
            return
        render_answer(data)
        if comments:
            _print_comments(ctx, client, f"/api/v4/answers/{answer_id}/comments", limit)


def article(
    ctx: typer.Context,
    article_id: int = typer.Argument(..., help="文章 ID"),
    comments: bool = typer.Option(False, "--comments", "-c", help="附带评论"),
    limit: int = typer.Option(20, "--limit", "-n", min=1, max=100, help="评论条数"),
) -> None:
    """查看专栏文章全文。"""
    client = require_client(ctx)
    with client:
        data = client.get(f"/api/v4/articles/{article_id}", include=_ARTICLE_INCLUDE)
        if emit(ctx, data):
            return
        render_article(data)
        if comments:
            _print_comments(ctx, client, f"/api/v4/articles/{article_id}/comments", limit)


def comments(
    ctx: typer.Context,
    answer_id: int = typer.Option(None, "--answer", help="回答 ID"),
    article_id: int = typer.Option(None, "--article", help="文章 ID"),
    limit: int = typer.Option(20, "--limit", "-n", min=1, max=100),
) -> None:
    """查看回答或文章的评论。"""
    if bool(answer_id) == bool(article_id):
        raise typer.BadParameter("请且仅请指定 --answer 或 --article")
    path = (f"/api/v4/answers/{answer_id}/comments" if answer_id
            else f"/api/v4/articles/{article_id}/comments")
    client = require_client(ctx)
    with client:
        _print_comments(ctx, client, path, limit)
