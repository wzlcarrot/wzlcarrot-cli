"""Guarded tool pipeline: pre/post hooks around tool execution.

Mirrors DeepSeek Harness's ``tools/pre-execute`` / ``tools/post-execute``
waterfalls, scaled to a Python CLI.  Hooks may:

* **pre**: allow, ``deny`` (block with a reason), ``ask`` (require user
  confirmation), or rewrite the tool arguments;
* **post**: rewrite or annotate the tool result.

Hooks come from plugins (``api.hook(...)``) and from a declarative rules file
``~/.config/zhihu-cli/hooks.json``.  A throwing hook is contained so one bad
hook can never break the pipeline.
"""

from __future__ import annotations

import fnmatch
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import config_dir
from .output import error_console

PRE_EXECUTE = "pre_execute"
POST_EXECUTE = "post_execute"

# (event, matcher, fn, source)
_Hook = tuple[str, str, Callable[..., Any], str]


@dataclass
class HookResult:
    decision: str = "allow"  # allow | deny | ask
    reason: str = ""
    args: dict[str, Any] | None = None
    result: Any | None = None
    context: str = ""


def matches(matcher: str, name: str) -> bool:
    if matcher in ("*", "", None):
        return True
    return fnmatch.fnmatchcase(name, matcher)


class HookRegistry:
    def __init__(self) -> None:
        self._hooks: list[_Hook] = []

    def add(
        self,
        event: str,
        fn: Callable[..., Any],
        matcher: str = "*",
        source: str = "",
    ) -> None:
        self._hooks.append((event, matcher, fn, source))

    def entries(self) -> list[_Hook]:
        return list(self._hooks)

    def run_pre(self, name: str, args: dict[str, Any]) -> HookResult | None:
        combined = HookResult()
        changed = False
        for event, matcher, fn, _source in self._hooks:
            if event != PRE_EXECUTE or not matches(matcher, name):
                continue
            try:
                out = fn(name, dict(args))
            except Exception as exc:  # noqa: BLE001 - contain callback exceptions
                error_console.print(f"[yellow]pre-hook 异常：{exc}[/yellow]")
                continue
            if out is None:
                continue
            if out.decision == "deny":
                return out
            if out.decision == "ask":
                combined.decision = "ask"
                combined.reason = out.reason or combined.reason
            if out.args is not None:
                combined.args = out.args
                changed = True
        if combined.decision == "allow" and not changed:
            return None
        return combined

    def run_post(self, name: str, args: dict[str, Any], result: Any) -> Any:
        for event, matcher, fn, _source in self._hooks:
            if event != POST_EXECUTE or not matches(matcher, name):
                continue
            try:
                out = fn(name, args, result)
            except Exception as exc:  # noqa: BLE001 - contain callback exceptions
                error_console.print(f"[yellow]post-hook 异常：{exc}[/yellow]")
                continue
            if out is None:
                continue
            if out.result is not None:
                result = out.result
            if out.context:
                if isinstance(result, dict):
                    existing = str(result.get("_hook_context") or "")
                    result = {**result, "_hook_context": (existing + out.context).strip()}
                else:
                    result = {"result": result, "_hook_context": out.context}
        return result


def hooks_file() -> Path:
    return config_dir() / "hooks.json"


def _rule_hook(rule: dict[str, Any]) -> Callable[..., Any]:
    action = str(rule.get("action", "deny"))
    message = str(rule.get("message", ""))
    field = rule.get("field")
    pattern = rule.get("pattern")

    def hook(name: str, args: dict[str, Any]) -> HookResult | None:
        if field is not None:
            if not isinstance(args, dict) or field not in args:
                return None
            if pattern is not None and not re.search(str(pattern), str(args[field])):
                return None
        return HookResult(decision=action, reason=message)

    return hook


def load_rules(registry: HookRegistry) -> int:
    path = hooks_file()
    if not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        error_console.print(f"[yellow]hooks.json 解析失败：{exc}[/yellow]")
        return 0
    rules = data.get("hooks", data) if isinstance(data, dict) else data
    count = 0
    for rule in rules if isinstance(rules, list) else []:
        if not isinstance(rule, dict):
            continue
        if str(rule.get("event", PRE_EXECUTE)) != PRE_EXECUTE:
            continue
        tools = rule.get("tools", "*")
        matchers = tools if isinstance(tools, list) else [tools]
        for matcher in matchers:
            registry.add(PRE_EXECUTE, _rule_hook(rule), str(matcher), "hooks.json")
            count += 1
    return count


def load_hooks(hooks: list[tuple[str, str, Callable[..., Any]]] | None = None) -> HookRegistry:
    """Build a registry from plugin hooks plus the declarative rules file."""
    registry = HookRegistry()
    for event, matcher, fn in hooks or []:
        registry.add(event, fn, matcher or "*", "plugin")
    load_rules(registry)
    return registry
