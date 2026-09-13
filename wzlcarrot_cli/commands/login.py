"""Login, logout and status commands."""

from __future__ import annotations

from pathlib import Path

import typer

from ..client import ZhihuClient
from ..config import config_dir
from ..output import console, error_console
from ..qrlogin import qr_login
from ..session import Credentials, clear_credentials


def _load_cookie_input(cookie: str | None, cookie_file: Path | None) -> str | None:
    if cookie:
        return cookie
    if cookie_file:
        return cookie_file.read_text(encoding="utf-8").strip()
    return None


def _validate(credentials: Credentials, *, verbose: bool = True) -> dict:
    if not credentials.d_c0:
        error_console.print("[yellow]警告[/yellow] 缺少 d_c0 Cookie，签名会失败。")
    client = ZhihuClient(credentials, min_delay=0.0, max_delay=0.0)
    try:
        me = client.get("/api/v4/me")
    finally:
        client.close()
    if verbose:
        console.print(f"[green]登录成功[/green] {me.get('name', '')} (@{me.get('url_token', '')})")
    return me


def login(
    cookie: str = typer.Option(None, "--cookie", "-c", help="改用浏览器 Cookie 字符串登录"),
    cookie_file: Path = typer.Option(None, "--cookie-file", help="从文件读取 Cookie 字符串"),
    qr: bool = typer.Option(False, "--qr", help="改为显示二维码（默认只给登录链接）"),
) -> None:
    """登录知乎。默认给出一条登录链接；也可用 --cookie 手动粘贴 Cookie。"""
    raw = _load_cookie_input(cookie, cookie_file)
    if raw:
        try:
            credentials = Credentials.from_cookie_string(raw)
        except ValueError as exc:
            error_console.print(f"Cookie 解析失败：{exc}")
            raise typer.Exit(code=1) from exc
    else:
        credentials = qr_login(show_qr=qr)

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
