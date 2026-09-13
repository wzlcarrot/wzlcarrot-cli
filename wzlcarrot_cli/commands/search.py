"""Search command."""

from __future__ import annotations

import typer

from ..output import render_search
from ._common import emit, require_client


def search(
    ctx: typer.Context,
    query: list[str] = typer.Argument(..., help="搜索关键词"),
    limit: int = typer.Option(20, "--limit", "-n", min=1, max=50),
    offset: int = typer.Option(0, "--offset", min=0),
) -> None:
    """综合搜索知乎内容。"""
    keyword = " ".join(query)
    client = require_client(ctx)
    params = {
        "t": "general",
        "q": keyword,
        "correction": 1,
        "offset": offset,
        "limit": limit,
        "lc_idx": 0,
        "show_all_topics": 0,
        "search_hash_id": "",
        "vertical_info": "0,0,0,0,0,0,0,0,0,0",
    }
    with client:
        data = client.request("GET", "/api/v4/search_v3", params=params)
    if emit(ctx, data):
        return
    render_search(data.get("data", []))
