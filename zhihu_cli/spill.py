"""Spill oversized tool results to private files.

When a tool result is too large to inline, we persist the full text to a
session-scoped file and hand the model a short head/tail preview plus an opaque
locator it can re-read with the ``read_spill`` tool.  Mirrors DeepSeek
Harness's spill seam, scaled down.

Storage hardening (see DeepSeek Harness ``docs/defensive-patterns.md``):
a private 0700 root, a per-session subdirectory, and exclusive owner-only
``O_EXCL``/0600 creation so a planted symlink cannot redirect the write.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from .config import config_dir
from .exceptions import ZhihuError

DEFAULT_HEAD = 1500
DEFAULT_TAIL = 800


@dataclass
class SpillRef:
    locator: str
    bytes: int
    retrieval_hint: str


def spill_root() -> Path:
    root = config_dir() / "spill"
    root.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(root, 0o700)
    except OSError:
        pass
    return root


def _session_dir(session_id: str) -> Path:
    safe = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:16]
    path = spill_root() / f"session-{safe}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def _safe_name(name: str) -> str:
    cleaned = "".join(ch for ch in name if ch.isalnum() or ch in "-_.").strip("._")
    return cleaned[:40] or "result"


def preview(text: str, head: int = DEFAULT_HEAD, tail: int = DEFAULT_TAIL) -> str:
    if len(text) <= head + tail:
        return text
    return f"{text[:head]}\n…[中间省略 {len(text) - head - tail} 字]…\n{text[-tail:]}"


def save_text(session_id: str, tool_name: str, call_id: str, label: str, content: str) -> SpillRef:
    directory = _session_dir(session_id)
    filename = f"{secrets.token_hex(6)}-{_safe_name(tool_name)}-{_safe_name(label)}.txt"
    path = directory / filename
    data = content.encode("utf-8")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    return SpillRef(
        locator=str(path),
        bytes=len(data),
        retrieval_hint="用 read_spill(path, offset, limit) 读取完整内容",
    )


def read_spill(locator: str, offset: int = 0, limit: int = 8000) -> str:
    path = Path(locator).resolve()
    root = spill_root().resolve()
    if not path.is_relative_to(root):
        raise ZhihuError("read_spill 只能读取本工具的溢出目录")
    if not path.is_file():
        raise ZhihuError(f"溢出文件不存在：{locator}")
    text = path.read_text(encoding="utf-8", errors="replace")
    offset = max(0, offset)
    if limit <= 0:
        return text[offset:]
    return text[offset:offset + limit]


def list_spills() -> list[Path]:
    return sorted(spill_root().rglob("*.txt"))


def clean_spills() -> int:
    removed = 0
    for path in list_spills():
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed
