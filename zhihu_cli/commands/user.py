"""User and profile commands."""

from __future__ import annotations

import typer

from ..output import console, render_answer, render_member
from ._common import emit, require_client

_MEMBER_INCLUDE = (
    "name,url_token,headline,description,answer_count,articles_count,"
    "followers_count,following_count,avatar_url,gender"
)


def user(
    ctx: typer.Context,
    token: str = typer.Argument(..., help="用户 url_token（个人主页 URL 末段）"),
    limit: int = typer.Option(10, "--limit", "-n", min=1, max=50, help="附带回答条数"),
) -> None:
    """查看用户主页（可选最近回答）。"""
    client = require_client(ctx)
    with client:
        data = client.get(f"/api/v4/members/{token}", include=_MEMBER_INCLUDE)
        if emit(ctx, data):
            return
        render_member(data)
        if limit > 0:
            params = {"include": "data[*].content", "sort_by": "created"}
            items = list(
                client.paginate(
                    f"/api/v4/members/{token}/answers", params, limit=20, max_items=limit
                )
            )
            if items:
                console.print("\n[bold]最近回答[/bold]")
                for item in items:
                    render_answer(item, show_content=False)


def me(ctx: typer.Context) -> None:
    """查看当前登录账号信息。"""
    client = require_client(ctx)
    with client:
        data = client.get("/api/v4/me", include=_MEMBER_INCLUDE)
    if emit(ctx, data):
        return
    render_member(data)


def following(
    ctx: typer.Context,
    token: str = typer.Option(None, "--user", help="url_token，默认自己"),
    limit: int = typer.Option(20, "--limit", "-n", min=1, max=100),
) -> None:
    """列出关注的用户。"""
    client = require_client(ctx)
    with client:
        if not token:
            token = client.me().get("url_token", "")
        data = client.following(token, limit=limit)
    if emit(ctx, data):
        return
    for item in data.get("data", []):
        console.print(f"{item.get('name', '')}  [dim]@{item.get('url_token', '')}[/dim]  "
                      f"{item.get('headline', '')}")


def collections(
    ctx: typer.Context,
    token: str = typer.Option(None, "--user", help="url_token，默认自己"),
    limit: int = typer.Option(20, "--limit", "-n", min=1, max=100),
) -> None:
    """列出收藏夹。"""
    client = require_client(ctx)
    with client:
        data = client.favlists(token, limit=limit)
    if emit(ctx, data):
        return
    for item in data.get("data", []):
        console.print(
            f"[cyan]{item.get('title', '')}[/cyan]  "
            f"({item.get('answer_count', 0)} 条)  id={item.get('id')}"
        )


def followers(
    ctx: typer.Context,
    token: str = typer.Option(None, "--user", help="url_token，默认自己"),
    limit: int = typer.Option(20, "--limit", "-n", min=1, max=100),
) -> None:
    """列出粉丝。"""
    client = require_client(ctx)
    with client:
        if not token:
            token = client.me().get("url_token", "")
        data = client.followers(token, limit=limit)
    if emit(ctx, data):
        return
    for item in data.get("data", []):
        console.print(f"{item.get('name', '')}  [dim]@{item.get('url_token', '')}[/dim]  "
                      f"{item.get('headline', '')}")


def notifications(
    ctx: typer.Context,
    limit: int = typer.Option(10, "--limit", "-n", min=1, max=50),
    entry: str = typer.Option("all", "--entry", help="all / vote_thank / comment / follow"),
) -> None:
    """查看通知消息。"""
    client = require_client(ctx)
    with client:
        data = client.notifications(limit=limit, entry_name=entry)
    if emit(ctx, data):
        return
    for item in data.get("data", []):
        text = (item.get("content") or {}).get("text") or item.get("text") or ""
        actor = (item.get("actors") or [{}])[0].get("name", "") if item.get("actors") else ""
        console.print(f"[green]{actor}[/green] {text}".strip())
