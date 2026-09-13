"""``wzlcarrot license`` — activate and inspect Pro license keys."""

from __future__ import annotations

import time

import typer

from ..license import activate as activate_key
from ..license import current_status
from ..license import deactivate as deactivate_key
from ..output import console, error_console

license_app = typer.Typer(help="License 激活与状态（free / pro）")


@license_app.command("status")
def status() -> None:
    """查看当前版本分层与授权信息。"""
    info = current_status()
    tier = "pro" if info.is_pro else "free"
    console.print(f"当前： [bold]{tier}[/bold]")
    if info.valid:
        if info.email:
            console.print(f"授权： {info.email}")
        if info.expires:
            expires = time.strftime("%Y-%m-%d", time.localtime(info.expires))
            console.print(f"到期： {expires}")
    else:
        console.print("[dim]未激活 Pro。运行 `wzlcarrot license activate <key>`[/dim]")


@license_app.command("activate")
def activate(key: str = typer.Argument(..., help="License key")) -> None:
    """激活 Pro License。"""
    try:
        info = activate_key(key)
    except Exception as exc:
        error_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    tier = "pro" if info.is_pro else "free"
    console.print(f"[green]已激活[/green] 分层：{tier}" + (f"（{info.email}）" if info.email else ""))


@license_app.command("deactivate")
def deactivate() -> None:
    """移除本机 License。"""
    if deactivate_key():
        console.print("[green]已移除 License[/green]")
    else:
        console.print("本机无 License。")
