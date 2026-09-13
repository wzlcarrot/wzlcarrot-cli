"""Persist and resume chat sessions under ``~/.config/wzlcarrot-cli/sessions``."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import config_dir
from .exceptions import ZhihuError


def sessions_dir() -> Path:
    path = config_dir() / "sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_session_id() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y%m%d-%H%M%S")


def _session_path(session_id: str) -> Path:
    safe = "".join(ch for ch in session_id if ch.isalnum() or ch in "-_")
    return sessions_dir() / f"{safe}.json"


def _title_from_messages(messages: list[dict[str, Any]]) -> str:
    for message in messages:
        if message.get("role") == "user":
            text = str(message.get("content") or "").strip().replace("\n", " ")
            if text:
                return text[:40]
    return "（空会话）"


@dataclass
class SessionInfo:
    id: str
    title: str
    updated: float
    messages: int
    model: str = ""


def save_session(
    session_id: str, messages: list[dict[str, Any]], *, model: str = ""
) -> Path:
    path = _session_path(session_id)
    now = datetime.now(timezone.utc).timestamp()
    created = now
    if path.exists():
        try:
            created = json.loads(path.read_text(encoding="utf-8")).get("created", now)
        except (OSError, ValueError):
            pass
    payload = {
        "id": session_id,
        "created": created,
        "updated": now,
        "model": model,
        "title": _title_from_messages(messages),
        "messages": messages,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    path.chmod(0o600)
    return path


def load_session(session_id: str | None = None) -> tuple[str, list[dict[str, Any]]]:
    """Load a session by id, or the most recent one when id is None."""
    path = _session_path(session_id) if session_id else None
    if path is None or not path.exists():
        latest = latest_session()
        if latest is None:
            raise ZhihuError("没有可恢复的会话")
        path = latest
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ZhihuError(f"会话文件损坏：{exc}") from exc
    return str(data.get("id", path.stem)), list(data.get("messages", []))


def list_sessions() -> list[SessionInfo]:
    infos: list[SessionInfo] = []
    for path in sessions_dir().glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        infos.append(SessionInfo(
            id=str(data.get("id", path.stem)),
            title=str(data.get("title", "")),
            updated=float(data.get("updated", 0.0)),
            messages=len(data.get("messages", [])),
            model=str(data.get("model", "")),
        ))
    infos.sort(key=lambda s: s.updated, reverse=True)
    return infos


def latest_session() -> Path | None:
    files = list(sessions_dir().glob("*.json"))
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)
