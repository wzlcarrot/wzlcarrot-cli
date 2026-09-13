from __future__ import annotations

import pytest
from typer.testing import CliRunner

from wzlcarrot_cli.cli import app, root_app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _no_update_check(monkeypatch):
    monkeypatch.setenv("WZLCARROT_CLI_NO_UPDATE_CHECK", "1")


def test_root_version():
    result = runner.invoke(root_app, ["version"])
    assert result.exit_code == 0
    assert "wzlcarrot" in result.output


def test_root_nests_zhihu():
    # Platforms live under the umbrella: `wzlcarrot zhihu ...`.
    assert runner.invoke(root_app, ["zhihu", "--help"]).exit_code == 0


def test_zhihu_app_has_platform_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "hot" in result.output and "comment" in result.output


def test_generic_commands_not_under_zhihu():
    # strict layering: generic commands live at the umbrella level only
    for args in (["version"], ["connect"], ["doctor"]):
        assert runner.invoke(app, args).exit_code != 0


def test_generic_commands_available_at_root():
    for args in (["plugins"], ["connect", "--list"], ["doctor", "--offline"], ["sessions"]):
        result = runner.invoke(root_app, args)
        assert result.exit_code == 0, (args, result.output)


def test_platform_only_command_not_at_root():
    assert runner.invoke(root_app, ["hot"]).exit_code != 0

