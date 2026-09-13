from __future__ import annotations

import pytest
import typer
from typer.testing import CliRunner

from wzlcarrot_cli import cli, platforms
from wzlcarrot_cli.platforms import Platform, all_platforms, get, register

runner = CliRunner()


@pytest.fixture(autouse=True)
def _no_update(monkeypatch):
    monkeypatch.setenv("ZHIHU_CLI_NO_UPDATE_CHECK", "1")


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


def test_root_app_wires_discovered_platforms(monkeypatch):
    def build():
        sub = typer.Typer()

        @sub.command("ping")
        def ping() -> None:
            typer.echo("pong")

        return sub

    monkeypatch.setattr(
        cli, "discover", lambda: [Platform("demo", "Demo", build, source="test")]
    )
    root = cli.build_root_app()
    result = runner.invoke(root, ["demo", "ping"])
    assert result.exit_code == 0
    assert "pong" in result.output


def test_root_app_includes_zhihu():
    help_text = runner.invoke(cli.build_root_app(), ["--help"]).output
    assert "zhihu" in help_text
