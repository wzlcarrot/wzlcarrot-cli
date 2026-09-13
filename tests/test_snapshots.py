"""Keyless snapshot tests.

These pin the model-visible contract — the base system prompt and the built-in
tool schemas — so an accidental edit is caught instead of silently changing how
the agent behaves.  Refresh intentionally with::

    UPDATE_SNAPSHOTS=1 uv run pytest tests/test_snapshots.py

Borrowed from DeepSeek Harness's snapshot testing policy.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from wzlcarrot_cli.commands.chat import _tools_spec, base_system_prompt

SNAPSHOT_DIR = Path(__file__).parent / "snapshots"
UPDATE = os.environ.get("UPDATE_SNAPSHOTS") == "1"


def _check(name: str, actual: str) -> None:
    path = SNAPSHOT_DIR / name
    if UPDATE:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8")
        return
    assert path.exists(), f"缺少快照 {name}，运行 UPDATE_SNAPSHOTS=1 pytest 生成"
    expected = path.read_text(encoding="utf-8")
    assert actual == expected, (
        f"快照 {name} 变化了；确认无误后运行 UPDATE_SNAPSHOTS=1 pytest 刷新"
    )


def _stable_prompt() -> str:
    # The base prompt embeds the current time; normalize it for stable snapshots.
    return re.sub(r"当前时间：[^。]*。", "当前时间：<TIMESTAMP>。", base_system_prompt())


def test_system_prompt_snapshot():
    _check("system_prompt.txt", _stable_prompt() + "\n")


def test_tool_schemas_snapshot():
    specs = _tools_spec()
    rendered = json.dumps(specs, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _check("tools.json", rendered)


def test_tool_names_are_stable_and_unique():
    names = [spec["function"]["name"] for spec in _tools_spec()]
    assert len(names) == len(set(names)), "工具名重复"
    # A small guard so accidental removal of core tools is obvious.
    for expected in ("hot", "search", "answer", "vote", "compose_publish"):
        assert expected in names
