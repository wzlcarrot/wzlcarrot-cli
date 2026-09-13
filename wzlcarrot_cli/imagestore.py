"""Localize images referenced in exported content.

Downloads ``<img src>`` targets into a per-export directory and rewrites the
HTML to point at the local files, so an exported Markdown folder is a
self-contained archive instead of a list of soon-to-rot remote links.
"""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .config import BASE_URL, browser_headers
from .output import console

_IMG_TAG_RE = re.compile(r'<img\b[^>]*?\bsrc="([^"]+)"', re.IGNORECASE)
_EXT_BY_TYPE = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/svg+xml": ".svg",
}
_DEFAULT_DELAY = 1.0


def _absolute(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    return url


def _fetch(url: str, *, referer: str, timeout: float = 20.0) -> tuple[str, bytes] | None:
    headers = browser_headers()
    headers["referer"] = referer
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
    except httpx.HTTPError:
        return None
    if resp.status_code != 200 or not resp.content:
        return None
    return resp.headers.get("content-type", ""), resp.content


def _extension(url: str, content_type: str) -> str:
    name = Path(urlparse(url).path).name
    if "." in name:
        ext = "." + name.rsplit(".", 1)[1].lower()
        if len(ext) <= 6:
            return ext
    return _EXT_BY_TYPE.get(content_type.split(";")[0].strip().lower(), ".jpg")


def localize_images(
    html: str,
    dest_dir: Path,
    rel_prefix: str,
    *,
    delay: float = _DEFAULT_DELAY,
    referer: str = f"{BASE_URL}/",
) -> tuple[str, int]:
    """Download images in ``html`` into ``dest_dir`` and rewrite their ``src``.

    Returns the rewritten HTML and the number of images downloaded.  Failures
    leave the original remote URL in place.
    """
    urls = []
    for raw in _IMG_TAG_RE.findall(html):
        url = _absolute(raw)
        if url.startswith("data:") or url in urls:
            continue
        urls.append(url)
    if not urls:
        return html, 0

    dest_dir.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}
    count = 0
    for url in urls:
        fetched = _fetch(url, referer=referer)
        if fetched is None:
            console.print(f"[dim]跳过（下载失败）{url[:60]}[/dim]")
            continue
        content_type, data = fetched
        ext = _extension(url, content_type)
        filename = hashlib.md5(url.encode("utf-8")).hexdigest()[:10] + ext
        (dest_dir / filename).write_bytes(data)
        mapping[url] = f"{rel_prefix}/{filename}"
        count += 1
        if delay:
            time.sleep(delay)

    if not mapping:
        return html, 0

    def replace(match: re.Match[str]) -> str:
        local = mapping.get(_absolute(match.group(1)))
        return match.group(0) if not local else match.group(0).replace(match.group(1), local, 1)

    console.print(f"[dim]已归档 {count} 张图片到 {dest_dir}[/dim]")
    return _IMG_TAG_RE.sub(replace, html), count
