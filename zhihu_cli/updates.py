"""Lightweight update check against PyPI.

Cached for a day, opt-out via ``ZHIHU_CLI_NO_UPDATE_CHECK``, and designed to
never break or slow down a command: any failure is swallowed. The only network
call is the public PyPI JSON endpoint - no telemetry.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

from .config import config_dir

PYPI_JSON_URL = "https://pypi.org/pypi/zhihu-cli/json"
CHECK_INTERVAL = 24 * 3600.0
NO_CHECK_ENV = "ZHIHU_CLI_NO_UPDATE_CHECK"


def _cache_path() -> Path:
    return config_dir() / "update_check.json"


def _read_cache() -> dict[str, Any]:
    try:
        data = json.loads(_cache_path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {}


def _write_cache(latest: str, checked_at: float) -> None:
    path = _cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"latest": latest, "checked_at": checked_at}), encoding="utf-8"
        )
    except OSError:
        pass


def parse_version(version: str) -> tuple[int, ...]:
    """Numeric dotted-version tuple; ignores any pre-release suffix."""
    parts: list[int] = []
    for piece in version.strip().split("."):
        digits = ""
        for ch in piece:
            if not ch.isdigit():
                break
            digits += ch
        parts.append(int(digits or 0))
    return tuple(parts)


def fetch_latest_version(timeout: float = 2.0) -> str | None:
    """Latest version published on PyPI, or ``None`` on any failure."""
    try:
        resp = httpx.get(PYPI_JSON_URL, timeout=timeout)
        if resp.status_code != 200:
            return None
        version = str(resp.json().get("info", {}).get("version") or "")
        return version or None
    except Exception:  # noqa: BLE001 - an update check must never fail a command
        return None


def check_for_update(current: str, *, now: float | None = None) -> str | None:
    """Return the newer version string if one exists on PyPI, else ``None``.

    The PyPI answer is cached for :data:`CHECK_INTERVAL`; a stale or missing
    cache triggers one query. Respects :data:`NO_CHECK_ENV`.
    """
    if os.environ.get(NO_CHECK_ENV):
        return None
    now = time.time() if now is None else now
    cache = _read_cache()
    latest = cache.get("latest")
    checked_at = float(cache.get("checked_at") or 0.0)
    if not latest or (now - checked_at) >= CHECK_INTERVAL:
        latest = fetch_latest_version()
        if latest is None:
            return None  # leave the old cache untouched on transient failures
        _write_cache(latest, now)
    if parse_version(latest) > parse_version(current):
        return latest
    return None
