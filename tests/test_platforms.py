from __future__ import annotations

import pytest
import typer
from typer.testing import CliRunner

from wzlcarrot_cli import cli, platforms
from wzlcarrot_cli.platforms import Platform, all_platforms, get, register

runner = CliRunner()


@pytest.fixture(autouse=True)
def _no_update(monkeypatch):
    monkeypatch.setenv("WZLCARROT_CLI_NO_UPDATE_CHECK", "1")


def test_builtin_zhihu_is_registered():
    platform = get("zhihu")
    assert platform is not None
    assert platform.title


def test_register_and_get_with_cleanup():
    platform = Platform("tmpdemo", "Tmp", lambda: typer.Typer(), source="test")
    register(platform)
    try:
        assert get("tmpdemo") is platform
        assert any(p.name == "tmpdemo" for p in all_platforms())
    finally:
        platforms._REGISTRY.pop("tmpdemo", None)


def test_platforms_command_lists_registered(monkeypatch):
    monkeypatch.setattr(
        cli, "discover", lambda: [Platform("demo", "Demo", lambda: typer.Typer(), source="test")]
    )
    result = runner.invoke(cli.build_root_app(), ["platforms"])
    assert result.exit_code == 0
    assert "demo" in result.output


def test_root_app_nests_platforms():
    # Platforms now live under the umbrella too: `wzlcarrot zhihu hot`.
    root = cli.build_root_app()
    assert runner.invoke(root, ["zhihu", "--help"]).exit_code == 0
    assert runner.invoke(root, ["zhihu", "hot", "--help"]).exit_code == 0


def test_planned_platforms_are_registered_and_nested():
    for name in ("weibo", "xiaohongshu"):
        platform = get(name)
        assert platform is not None and platform.source == "planned"
    root = cli.build_root_app()
    result = runner.invoke(root, ["weibo", "status"])
    assert result.exit_code == 0
    assert "规划中" in result.output


def test_platforms_command_shows_planned():
    result = runner.invoke(cli.build_root_app(), ["platforms"])
    assert result.exit_code == 0
    assert "zhihu" in result.output
    assert "weibo" in result.output
    assert "xiaohongshu" in result.output


def test_zhihu_app_exposes_platform_commands():
    help_text = runner.invoke(cli.app, ["--help"]).output
    assert "hot" in help_text and "login" in help_text


def test_active_platform_is_zhihu_by_default():
    platform = platforms.active()
    assert platform is not None
    assert platform.name == "zhihu"


def test_active_falls_back_to_first_tool_platform():
    saved_registry = dict(platforms._REGISTRY)
    platforms._REGISTRY.clear()
    platforms.set_active(None)
    try:
        assert platforms.active() is None
        register(Platform("demo", "Demo", lambda: typer.Typer(), build_tools=lambda client: []))
        active = platforms.active()
        assert active is not None and active.name == "demo"
    finally:
        platforms._REGISTRY.clear()
        platforms._REGISTRY.update(saved_registry)
        platforms.set_active("zhihu")


def test_platform_tools_for_uses_active_platform():
    from wzlcarrot_cli.commands.chat import _platform_tools_for

    names = {tool.name for tool in _platform_tools_for(object())}
    assert {"hot", "search", "vote"} <= names
