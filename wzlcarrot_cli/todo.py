"""A lightweight task list the agent maintains for multi-step work.

Borrowed from DeepSeek Harness's ``todo``/``plan`` packages and Claude Code's
TodoWrite: the model calls ``todo_write`` with the full list each time, and the
TUI shows it in a live panel.
"""

from __future__ import annotations

from typing import Any

STATUSES = ("pending", "in_progress", "completed")
ICONS = {"pending": "☐", "in_progress": "◐", "completed": "☑"}


def normalize(todos: Any) -> list[dict[str, str]]:
    """Keep only well-formed items; coerce unknown statuses to ``pending``."""
    cleaned: list[dict[str, str]] = []
    if not isinstance(todos, list):
        return cleaned
    for item in todos:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        status = str(item.get("status", "pending"))
        if status not in STATUSES:
            status = "pending"
        cleaned.append({"content": content, "status": status})
    return cleaned


def render_plain(todos: list[dict[str, str]]) -> str:
    return "\n".join(f"{ICONS.get(t.get('status'), '☐')} {t.get('content', '')}" for t in todos)


def render_markdown(todos: list[dict[str, str]]) -> str:
    return "\n".join(
        f"- {ICONS.get(t.get('status'), '☐')} {t.get('content', '')}" for t in todos
    )
