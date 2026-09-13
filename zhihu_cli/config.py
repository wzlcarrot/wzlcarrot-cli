"""Configuration and on-disk locations."""

from __future__ import annotations

import json
import os
from pathlib import Path

APP_NAME = "zhihu-cli"
# Distribution (PyPI) name; the ``zhihu-cli`` name is taken by another project.
DIST_NAME = "wzlcarrot-cli"
BASE_URL = "https://www.zhihu.com"
API_BASE = "https://www.zhihu.com"

# Single source of truth for the browser fingerprint so UA / sec-ch-ua agree.
CHROME_VERSION = "131"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    f"(KHTML, like Gecko) Chrome/{CHROME_VERSION}.0.0.0 Safari/537.36"
)

# Be deliberately gentle with Zhihu: all requests are spaced by [min, max]
# seconds, and write operations (POST/DELETE) wait at least this much.
DEFAULT_MIN_DELAY = 1.5
DEFAULT_MAX_DELAY = 3.5
DEFAULT_WRITE_MIN_DELAY = 8.0
# Minimum gap between *any* two Zhihu requests, enforced across separate
# processes via a state file so back-to-back CLI calls cannot burst.
DEFAULT_MIN_GAP = 3.0
# Extra spacing for endpoints that Zhihu guards more aggressively.
SENSITIVE_EXTRA_DELAY = 6.0
SENSITIVE_PATH_MARKERS = ("followers", "followees", "notifications")
# How long to back off after an anti-crawler warning.
ANTI_ABUSE_COOLDOWN = 120.0


def browser_headers() -> dict[str, str]:
    """Headers consistent with a real desktop Chrome session."""
    return {
        "user-agent": USER_AGENT,
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "referer": f"{BASE_URL}/",
        "sec-ch-ua": (
            '"Not:A-Brand";v="99", '
            f'"Google Chrome";v="{CHROME_VERSION}", '
            f'"Chromium";v="{CHROME_VERSION}"'
        ),
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }


def config_dir() -> Path:
    override = os.environ.get("ZHIHU_CLI_HOME")
    if override:
        path = Path(override).expanduser()
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
        path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def credentials_file() -> Path:
    return config_dir() / "credentials.json"


def qrcode_file() -> Path:
    return config_dir() / "qrcode.png"


def rate_state_file() -> Path:
    return config_dir() / "rate.json"


def read_last_request() -> float:
    """Epoch seconds of the last outgoing request (0.0 if unknown)."""
    try:
        return float(json.loads(rate_state_file().read_text(encoding="utf-8")).get("last", 0.0))
    except (OSError, ValueError, TypeError):
        return 0.0


def write_last_request(timestamp: float) -> None:
    try:
        rate_state_file().write_text(json.dumps({"last": timestamp}), encoding="utf-8")
    except OSError:
        pass


def default_download_dir() -> Path:
    return Path.cwd() / "downloads"
