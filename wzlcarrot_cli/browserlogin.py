"""Interactive login via a real (headed) Chromium through Playwright.

Opens the desktop sign-in page so you can log in with whatever the page offers
(QR shown in-page, password, SMS) — avoiding the mobile/"download the app"
redirect that the raw scan-login link can trigger.

Requires the optional ``browser`` extra:
``pip install 'wzlcarrot-cli[browser]'`` and ``playwright install chromium``.
"""

from __future__ import annotations

import contextlib
import time
from pathlib import Path

from .config import BASE_URL, USER_AGENT
from .exceptions import ZhihuError
from .output import console
from .session import Credentials

SIGNIN_URL = f"{BASE_URL}/signin?next=%2F"


def _launch(playwright, headless: bool):
    try:
        return playwright.chromium.launch(headless=headless)
    except Exception:  # fall back to a cached build
        cached = sorted(Path.home().glob(".cache/ms-playwright/chromium-*/chrome-linux64/chrome"))
        if cached:
            return playwright.chromium.launch(headless=headless, executable_path=str(cached[-1]))
        raise


def browser_login(*, timeout: int = 300, headless: bool = False) -> Credentials:
    """Open a real browser, let the user log in, and capture the session cookies."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ZhihuError(
            "需要 Playwright：pip install 'wzlcarrot-cli[browser]' 且 playwright install chromium"
        ) from exc

    with sync_playwright() as playwright:
        browser = _launch(playwright, headless)
        try:
            context = browser.new_context(user_agent=USER_AGENT)
            page = context.new_page()
            page.goto(SIGNIN_URL, wait_until="domcontentloaded", timeout=60000)
            console.print(
                "已打开浏览器窗口，请在窗口内登录知乎（扫码 / 密码 / 短信均可）；"
                "登录成功后会自动完成。"
            )

            deadline = time.time() + timeout
            while time.time() < deadline:
                cookies = {c["name"]: c["value"] for c in context.cookies()}
                if cookies.get("z_c0"):
                    # Seed the homepage so _xsrf / d_c0 are present too.
                    with contextlib.suppress(Exception):  # best effort
                        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
                    cookies = {c["name"]: c["value"] for c in context.cookies()}
                    return Credentials(cookies=cookies)
                time.sleep(2)
        finally:
            browser.close()
    raise ZhihuError("登录超时，请重试")
