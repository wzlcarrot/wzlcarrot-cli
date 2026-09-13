"""Hot list, recommendation feed and topic commands."""

from __future__ import annotations

import typer

from ..output import console, render_feed, render_hot
from ._common import emit, require_client


def hot(
    ctx: typer.Context,
    limit: int = typer.Option(50, "--limit", "-n", min=1, max=100, help="条数"),
) -> None:
    """知乎热榜。"""
    client = require_client(ctx)
    with client:
        data = client.hot_list(limit)
    if emit(ctx, data):
        return
    render_hot(data.get("data", [])[:limit])


def feed(
    ctx: typer.Context,
    limit: int = typer.Option(20, "--limit", "-n", min=1, max=50, help="条数"),
) -> None:
    """首页推荐流。"""
    client = require_client(ctx)
    with client:
        data = client.recommend_feed(limit)
    if emit(ctx, data):
        return
    render_feed(data.get("data", [])[:limit])


def topic(
    ctx: typer.Context,
    topic_id: str = typer.Argument(..., help="话题 ID"),
    questions: bool = typer.Option(False, "--questions", "-q", help="列出热门问题"),
    limit: int = typer.Option(10, "--limit", "-n", min=1, max=50),
) -> None:
    """查看话题详情。"""
    client = require_client(ctx)
    with client:
        data = client.topic(topic_id)
        if emit(ctx, data):
            return
        console.print(            f"[bold]{data.get('name', '')}[/bold]\n"
            f"{data.get('introduction', '')}\n"
            f"关注 {data.get('followers_count', 0)} · 问题 {data.get('questions_count', 0)}"
        )
        if questions:
            hot_q = client.topic_hot_questions(topic_id, limit=limit)
            for item in hot_q.get("data", []):
                target = item.get("target", {}) or item.get("question", {})
                console.print(f"  · {target.get('title', '')}  (id={target.get('id')})")
