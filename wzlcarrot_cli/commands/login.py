"""Login (via Microsoft Edge), logout and status."""

from __future__ import annotations

import typer

from ..client import ZhihuClient
from ..config import config_dir
from ..edgelogin import edge_login
from ..output import console, error_console
from ..session import Credentials, clear_credentials


def _validate(credentials: Credentials, *, verbose: bool = True) -> dict:
    client = ZhihuClient(credentials, min_delay=0.0, max_delay=0.0)
    try:
        me = client.get("/api/v4/me")
    finally:
        client.close()
    if verbose:
        console.print(f"[green]登录成功[/green] {me.get('name', '')} (@{me.get('url_token', '')})")
    return me


def login() -> None:
    """打开 Edge 窗口登录知乎，并保存凭证。"""
    credentials = edge_login()
    if not credentials.is_logged_in():
        error_console.print(
            "[yellow]警告[/yellow] Cookie 中缺少 d_c0 或 z_c0，可能不是登录态。"
        )
    _validate(credentials)
    credentials.save()
    console.print(f"凭证已保存到 {config_dir() / 'credentials.json'}")


def logout() -> None:
    """删除本地保存的登录凭证。"""
    if clear_credentials():
        console.print("[green]已注销[/green]")
    else:
        console.print("本地无凭证。")


def status() -> None:
    """查看当前登录状态。"""
    credentials = Credentials.load()
    if not credentials.is_logged_in():
        console.print("[yellow]未登录[/yellow] 运行 `zhihu login`。")
        raise typer.Exit(code=1)
    me = _validate(credentials, verbose=False)
    console.print(
        f"[green]已登录[/green] {me.get('name', '')} (@{me.get('url_token', '')})\n"
        f"回答 {me.get('answer_count', 0)} · 文章 {me.get('articles_count', 0)} · "
        f"关注者 {me.get('followers_count', 0)} · 关注 {me.get('following_count', 0)}"
    )
