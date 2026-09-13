"""Pluggable platform abstraction.

A *platform* contributes a CLI sub-app (and, optionally, agent tools and a
system-prompt section) to the ``wzlcarrot`` umbrella command.  Built-in zhihu is
registered by ``cli.py``; third-party platforms are discovered from the entry
point group ``wzlcarrot_cli.platforms``.

Adding a platform = implement :class:`Platform` and register it (or ship an
entry point returning one); the top-level CLI needs no changes.
"""

from __future__ import annotations

import importlib.metadata
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import typer

from ..output import error_console

ENTRY_POINT_GROUP = "wzlcarrot_cli.platforms"


@dataclass
class Platform:
    """One platform plugged into the ``wzlcarrot`` CLI."""

    name: str
    title: str
    builder: Callable[[], typer.Typer]
    credentials_factory: Callable[[], Any] | None = None
    client_factory: Callable[..., Any] | None = None
    build_tools: Callable[[Any], list[Any]] | None = None
    agent_tools: Callable[[], list[Any]] | None = None
    prompt_section: Callable[[], str] | None = None
    source: str = field(default="builtin")


_REGISTRY: dict[str, Platform] = {}


def register(platform: Platform) -> None:
    _REGISTRY[platform.name] = platform


def get(name: str) -> Platform | None:
    return _REGISTRY.get(name)


def all_platforms() -> list[Platform]:
    return list(_REGISTRY.values())


def _iter_entry_point_platforms():
    try:
        entries = importlib.metadata.entry_points()
        selected = (
            entries.select(group=ENTRY_POINT_GROUP)
            if hasattr(entries, "select")
            else entries.get(ENTRY_POINT_GROUP, [])
        )
    except Exception:  # noqa: BLE001 - discovery must never break startup
        return
    for entry in selected:
        yield entry.name, entry


def discover() -> list[Platform]:
    """Return all platforms, loading third-party ones from entry points once."""
    for name, entry in _iter_entry_point_platforms():
        if _REGISTRY.get(name):
            continue
        try:
            obj = entry.load()
            platform = obj() if callable(obj) and not isinstance(obj, Platform) else obj
            if isinstance(platform, Platform):
                platform.source = f"entrypoint:{name}"
                register(platform)
            else:
                error_console.print(f"[yellow]平台入口 {name} 未返回 Platform，已跳过[/yellow]")
        except Exception as exc:  # noqa: BLE001 - one bad platform can't break the app
            error_console.print(f"[yellow]平台入口 {name} 加载失败：{exc}[/yellow]")
    return all_platforms()
