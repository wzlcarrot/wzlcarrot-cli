"""Optional browser fallback for signature resilience.

When Zhihu changes its ``x-zse-96`` algorithm, the pure-Python signature starts
returning ``403``.  If Playwright is installed *and* the user opts in via
``ZHIHU_CLI_BROWSER_FALLBACK=1``, GET requests that hit a signature failure are
retried through a real headless browser, which signs the request itself.

Playwright is an optional dependency (``pip install 'wzlcarrot-cli[browser]'``);
this module never imports it unless the fallback is actually used.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

ENABLE_ENV = "ZHIHU_CLI_BROWSER_FALLBACK"
HOME_URL = "https://www.zhihu.com/"


def is_available() -> bool:
    """True if the optional Playwright dependency can be imported."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False
    return True


def is_enabled() -> bool:
    return os.environ.get(ENABLE_ENV) not in (None, "", "0", "false", "False")


def _parse_cookies(cookie_header: str, domain: str = ".zhihu.com") -> list[dict[str, Any]]:
    cookies = []
    for part in cookie_header.split(";"):
        if "=" in part:
            name, value = part.split("=", 1)
            cookies.append({
                "name": name.strip(),
                "value": value.strip(),
                "domain": domain,
                "path": "/",
            })
    return cookies


def browser_fetch(url: str, cookie_header: str, *, timeout: float = 30.0) -> Any | None:
    """Fetch ``url`` from a real browser context and return parsed JSON.

    Loads the Zhihu origin first so the request is same-origin (cookies apply
    and the site's own request signing is exercised), then returns ``None`` on
    any failure so callers can fall back to re-raising the original error.
    """
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context()
                context.add_cookies(_parse_cookies(cookie_header))
                page = context.new_page()
                page.goto(HOME_URL, wait_until="domcontentloaded", timeout=timeout * 1000)
                text = page.evaluate(
                    "async (u) => { const r = await fetch(u, {credentials: 'include'});"
                    " return await r.text(); }",
                    url,
                )
            finally:
                browser.close()
    except Exception:  # noqa: BLE001 - optional resilience, never break the caller
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def make_fallback(cookie_header: str) -> Callable[[str], Any] | None:
    """Return a browser fetch callable, or ``None`` when disabled/unavailable."""
    if not is_enabled() or not is_available():
        return None
    return lambda url: browser_fetch(url, cookie_header)
