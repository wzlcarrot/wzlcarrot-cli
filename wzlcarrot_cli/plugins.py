"""A lightweight plugin system.

Mirrors the spirit of DeepSeek Harness's "everything is a plugin", scaled to a
Python CLI: plugins contribute CLI commands and agent tools to a shared
registry, are discovered from entry points or a local directory, and their
registrations are scoped to the plugin (so a failed load cannot leak partial
state).

Discover plugins by:

1. Python entry points in group ``wzlcarrot_cli.plugins`` (packaged distributions).
2. ``*.py`` files in ``~/.config/wzlcarrot-cli/plugins/`` (local, drop-in).

A plugin is any module exposing ``register(api: PluginAPI) -> None``.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import config_dir, env
from .output import error_console

ENTRY_POINT_GROUP = "wzlcarrot_cli.plugins"


@dataclass
class ToolDef:
    """An agent tool contributed by a plugin.

    ``handler`` is called as ``handler(client, **arguments)`` and must return a
    JSON-serializable result.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]
    write: bool = False

    def spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class PluginInfo:
    name: str
    commands: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)


class PluginAPI:
    """The registration surface handed to each plugin's ``register`` function."""

    def __init__(self) -> None:
        self.commands: dict[str, Callable[..., Any]] = {}
        self.tools: dict[str, ToolDef] = {}
        self.prompts: list[tuple[int, str]] = []
        self.hooks: list[tuple[str, str, Callable[..., Any]]] = []
        self.plugins: list[PluginInfo] = []
        self._info: PluginInfo | None = None

    def command(self, name: str, fn: Callable[..., Any]) -> None:
        self.commands[name] = fn
        if self._info is not None:
            self._info.commands.append(name)

    def prompt_section(self, name: str, text: str, priority: int = 0) -> None:
        """Contribute a system-prompt section; higher priority sorts later."""
        self.prompts.append((priority, text))
        if self._info is not None:
            self._info.prompts.append(name)

    def hook(self, event: str, fn: Callable[..., Any], matcher: str = "*") -> None:
        """Register a pre/post-execute hook for tools matching ``matcher``."""
        self.hooks.append((event, matcher, fn))
        if self._info is not None:
            self._info.hooks.append(f"{event}:{matcher}")

    def tool(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: Callable[..., Any],
        *,
        write: bool = False,
    ) -> None:
        self.tools[name] = ToolDef(name, description, parameters, handler, write)
        if self._info is not None:
            self._info.tools.append(name)


def plugins_dir() -> Path:
    path = config_dir() / "plugins"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_path(path: Path):
    spec = importlib.util.spec_from_file_location(f"zhihu_plugin_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载插件 {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _iter_entry_point_plugins():
    try:
        entries = importlib.metadata.entry_points()
        selected = (
            entries.select(group=ENTRY_POINT_GROUP)
            if hasattr(entries, "select")
            else entries.get(ENTRY_POINT_GROUP, [])
        )
    except Exception:  # noqa: BLE001 - metadata must never break startup
        return
    for entry in selected:
        try:
            yield entry.name, entry.load()
        except Exception as exc:  # noqa: BLE001
            error_console.print(f"[yellow]插件入口 {entry.name} 加载失败：{exc}[/yellow]")


def _iter_local_plugins():
    for path in sorted(plugins_dir().glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            yield path.stem, _load_path(path)
        except Exception as exc:  # noqa: BLE001
            error_console.print(f"[yellow]本地插件 {path.name} 加载失败：{exc}[/yellow]")


def load_plugins() -> PluginAPI:
    api = PluginAPI()
    if env("NO_PLUGINS"):
        return api
    for name, module in [*_iter_entry_point_plugins(), *_iter_local_plugins()]:
        register = getattr(module, "register", None)
        if not callable(register):
            continue
        info = PluginInfo(name)
        api.plugins.append(info)
        api._info = info
        try:
            register(api)
        except Exception as exc:  # noqa: BLE001 - one bad plugin can't break the app
            error_console.print(f"[yellow]插件 {name} 注册失败：{exc}[/yellow]")
        finally:
            api._info = None
    return api
