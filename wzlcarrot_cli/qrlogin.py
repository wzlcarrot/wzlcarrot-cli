"""QR-code login through Zhihu's official web API (no browser required).

Flow:
  1. GET /signin  -> seed cookies
  2. POST /udid, GET /oauth/captcha (best effort)
  3. POST /api/v3/account/api/login/qrcode -> token + link
  4. Print the login ``link`` and poll ``.../{token}/scan_info``
  5. Collect cookies once the user confirms on the phone
"""

from __future__ import annotations

import contextlib
import time
from pathlib import Path

import httpx

from .config import BASE_URL, browser_headers, qrcode_file
from .exceptions import ZhihuError
from .output import console
from .session import Credentials

QRCODE_API = f"{BASE_URL}/api/v3/account/api/login/qrcode"
CAPTCHA_API = f"{BASE_URL}/api/v3/oauth/captcha/v2?type=captcha_sign_in"

_QR_CHARS = {
    (False, False): " ",
    (True, False): "▀",
    (False, True): "▄",
    (True, True): "█",
}


def render_terminal_qr(text: str) -> str:
    import qrcode

    qr = qrcode.QRCode(border=1)
    qr.add_data(text)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    lines = []
    for y in range(0, len(matrix), 2):
        top = matrix[y]
        bottom = matrix[y + 1] if y + 1 < len(matrix) else [False] * len(top)
        lines.append("".join(_QR_CHARS[(top[x], bottom[x])] for x in range(len(top))))
    return "\n".join(lines)


def save_qr_png(text: str, path: Path) -> None:
    import qrcode

    qrcode.make(text).save(path)


def _set_xsrf(session: httpx.Client) -> None:
    xsrf = session.cookies.get("_xsrf")
    if xsrf:
        session.headers["x-xsrftoken"] = xsrf


def _is_logged_in(session: httpx.Client, info: dict) -> bool:
    if session.cookies.get("z_c0"):
        return True
    status = info.get("status")
    if status in (0, 1):  # 0 = not scanned, 1 = scanned not confirmed
        return False
    if info.get("access_token") or info.get("user_id") is not None:
        return True
    login_status = str(info.get("login_status") or "").upper()
    if login_status in {"CONFIRMED", "LOGIN_SUCCESS", "SUCCESS", "OK", "LOGGED_IN"}:
        return True
    return bool(info.get("success") is True or info.get("logged_in") is True)


def _fetch_missing_cookies(session: httpx.Client, cookies: dict[str, str]) -> dict[str, str]:
    if "z_c0" in cookies and ({"_xsrf", "d_c0"} - cookies.keys()):
        try:
            session.get(f"{BASE_URL}/")
        except httpx.HTTPError:
            pass
        for cookie in session.cookies.jar:
            if cookie.name in ("_xsrf", "d_c0"):
                cookies[cookie.name] = cookie.value
    return cookies


def qr_login(
    *,
    timeout: int = 180,
    poll_interval: float = 1.5,
    show: bool = True,
    show_qr: bool = False,
) -> Credentials:
    """Run the QR/link login flow and return saved-able credentials.

    By default the raw login **link** is printed (open it in a browser that is
    already logged in, or on your phone).  Set ``show_qr`` to also render a
    terminal QR code.
    """
    headers = browser_headers()
    headers["x-requested-with"] = "fetch"
    with httpx.Client(headers=headers, follow_redirects=True, timeout=15.0) as session:
        for step in (
            lambda: session.get(f"{BASE_URL}/signin"),
            lambda: session.post(f"{BASE_URL}/udid", json={}),
            lambda: session.get(CAPTCHA_API),
        ):
            try:
                step()
            except httpx.HTTPError:
                pass

        _set_xsrf(session)
        try:
            resp = session.post(QRCODE_API, json={})
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ZhihuError(f"获取登录链接失败：{exc}") from exc

        token = data.get("token") or data.get("qrcode_token")
        link = data.get("link") or ""
        if not token or not link:
            raise ZhihuError(f"登录接口未返回 token/link：{data}")

        if show_qr:
            png_path = qrcode_file()
            try:
                save_qr_png(link, png_path)
            except Exception:  # noqa: BLE001 - QR image is a convenience only
                png_path = None  # type: ignore[assignment]
            with contextlib.suppress(Exception):  # QR rendering is best-effort
                console.print(render_terminal_qr(link))
            if png_path:
                console.print(f"二维码图片：{png_path}")

        if show:
            console.print(f"登录链接：[bold]{link}[/bold]")
            console.print("在已登录知乎的浏览器打开上面的链接（或用手机知乎 App 打开），确认登录即可。")
        console.print("等待确认中…")

        scan_url = f"{QRCODE_API}/{token}/scan_info"
        session.headers["referer"] = f"{BASE_URL}/signin?next=%2F"
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(poll_interval)
            _set_xsrf(session)
            try:
                resp = session.get(scan_url)
            except httpx.HTTPError:
                continue
            try:
                info = resp.json()
            except ValueError:
                info = {}
            if _is_logged_in(session, info):
                break

        cookies = {c.name: c.value for c in session.cookies.jar}
        cookies = _fetch_missing_cookies(session, cookies)
        if "z_c0" not in cookies:
            raise ZhihuError("扫码超时或未完成确认（未获取到 z_c0）")
        return Credentials(cookies=cookies)
