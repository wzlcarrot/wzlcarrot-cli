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
import subprocess
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
    if not isinstance(info, dict):
        return False
    status = info.get("status")
    if status in (0, 1):  # 0 = not scanned, 1 = scanned not confirmed
        return False
    if status in (3, 4):  # expired / cancelled
        return False
    if status == 2:  # confirmed on the phone
        return True
    if isinstance(status, int) and status > 2:
        return True
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


def _check_api_error(info: object) -> None:
    """Raise a clear error when Zhihu returns an error envelope (e.g. captcha)."""
    if not isinstance(info, dict):
        return
    error = info.get("error")
    if not isinstance(error, dict) or not error:
        return
    code = error.get("code")
    if error.get("need_login") or code in (40352, 100, "ZERR_NOT_LOGIN"):
        raise ZhihuError(
            f"扫码接口被人机验证拦截（code={code}）。请稍后再试，"
            "或改用 `zhihu login --cookie \"...\"` 手动登录。"
        )


def _open_image(path: Path) -> None:
    """Pop the QR PNG open in the OS image viewer (Windows via WSL)."""
    win = ""
    with contextlib.suppress(Exception):
        win = subprocess.run(
            ["wslpath", "-w", str(path)], capture_output=True, text=True, check=False, timeout=10
        ).stdout.strip()
    with contextlib.suppress(OSError):
        subprocess.Popen(["explorer.exe", win or str(path)])


def qr_login(
    *,
    timeout: int = 300,
    poll_interval: float = 1.5,
    show: bool = True,
    show_qr: bool = True,
    open_image: bool = True,
    refresh: bool = True,
) -> Credentials:
    """Scan-to-login: show a QR (and pop it open), with an expiry and auto-refresh.

    The QR is valid for a limited time; when it expires it is automatically
    refreshed, until the overall ``timeout`` is reached.
    """
    headers = browser_headers()
    headers["x-requested-with"] = "fetch"
    with httpx.Client(headers=headers, follow_redirects=True, timeout=15.0) as session:
        for step in (
            lambda: session.get(f"{BASE_URL}/signin"),
            lambda: session.post(f"{BASE_URL}/udid", json={}),
            lambda: session.get(CAPTCHA_API),
        ):
            with contextlib.suppress(httpx.HTTPError):
                step()

        deadline = time.time() + timeout
        while time.time() < deadline:
            _set_xsrf(session)
            try:
                data = session.post(QRCODE_API, json={}).json()
            except (httpx.HTTPError, ValueError) as exc:
                raise ZhihuError(f"获取登录二维码失败：{exc}") from exc
            _check_api_error(data)

            token = data.get("token") or data.get("qrcode_token")
            link = (data.get("link") or "").strip()
            # The API sometimes appends a path-like artifact (e.g. "?/api/login/qrcode").
            if link and "?" in link and link.split("?", 1)[1].startswith("/"):
                link = link.split("?", 1)[0]
            if not link and token:
                link = f"{BASE_URL}/account/scan/login/{token}"
            if not token or not link:
                raise ZhihuError(f"登录接口未返回 token/link：{data}")

            expires_at = float(data.get("expires_at") or 0) or (time.time() + 120)

            if show_qr:
                png_path = qrcode_file()
                saved = False
                with contextlib.suppress(Exception):
                    save_qr_png(link, png_path)
                    saved = True
                with contextlib.suppress(Exception):
                    console.print(render_terminal_qr(link))
                if saved:
                    if open_image:
                        _open_image(png_path)
                    console.print(f"二维码图片：{png_path}")

            if show:
                remaining = max(0, int(expires_at - time.time()))
                until = time.strftime("%H:%M:%S", time.localtime(expires_at))
                console.print(
                    f"请用[bold]知乎 App[/bold]扫码确认；二维码有效期至 [bold]{until}[/bold]"
                    f"（约 {remaining} 秒）"
                )

            scan_url = f"{QRCODE_API}/{token}/scan_info"
            session.headers["referer"] = f"{BASE_URL}/signin?next=%2F"
            last_status: object = None
            while time.time() < min(expires_at, deadline):
                time.sleep(poll_interval)
                _set_xsrf(session)
                try:
                    info = session.get(scan_url).json()
                except (httpx.HTTPError, ValueError):
                    info = {}
                _check_api_error(info)
                status = info.get("status") if isinstance(info, dict) else None
                if status != last_status:
                    if status == 1:
                        console.print("已扫描，请在手机上点击「确认登录」…")
                    elif status == 2 or (isinstance(status, int) and status > 2):
                        console.print("已确认，正在完成登录…")
                    elif status in (3, 4):
                        console.print("二维码已失效或被取消")
                    last_status = status
                if _is_logged_in(session, info):
                    cookies = {c.name: c.value for c in session.cookies.jar}
                    if "z_c0" not in cookies:
                        with contextlib.suppress(Exception):
                            session.get(f"{BASE_URL}/")
                        cookies = {c.name: c.value for c in session.cookies.jar}
                    cookies = _fetch_missing_cookies(session, cookies)
                    if "z_c0" in cookies:
                        return Credentials(cookies=cookies)
                if status in (3, 4):
                    break

            if not refresh:
                break
            console.print("二维码已过期，正在刷新…")

    raise ZhihuError("登录超时，请重试")
