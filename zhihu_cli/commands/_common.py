"""Shared helpers for the command modules."""

from __future__ import annotations

from dataclasses import dataclass

import typer

from ..client import ZhihuClient
from ..exceptions import NotLoggedInError
from ..output import error_console, print_json
from ..session import Credentials


@dataclass
class Settings:
    min_delay: float = 1.5
    max_delay: float = 3.5
    write_min_delay: float = 8.0
    min_gap: float = 3.0
    as_json: bool = False


def get_settings(ctx: typer.Context) -> Settings:
    settings = ctx.obj
    if isinstance(settings, Settings):
        return settings
    return Settings()


def require_client(ctx: typer.Context) -> ZhihuClient:
    settings = get_settings(ctx)
    credentials = Credentials.load()
    try:
        return ZhihuClient(
            credentials,
            min_delay=settings.min_delay,
            max_delay=settings.max_delay,
            write_min_delay=settings.write_min_delay,
            min_gap=settings.min_gap,
        )
    except NotLoggedInError as exc:
        error_console.print(f"[bold red]未登录[/bold red] {exc}")
        raise typer.Exit(code=2) from exc


def emit(ctx: typer.Context, data: object) -> bool:
    """Print raw JSON when ``--json`` is set. Returns True if handled."""
    if get_settings(ctx).as_json:
        print_json(data)
        return True
    return False
