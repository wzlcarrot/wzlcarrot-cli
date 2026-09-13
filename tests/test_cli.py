from __future__ import annotations

import pytest
from typer.testing import CliRunner

from wzlcarrot_cli.cli import app, root_app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _no_update_check(monkeypatch):
    monkeypatch.setenv("ZHIHU_CLI_NO_UPDATE_CHECK", "1")


def test_root_version():
    result = runner.invoke(root_app, ["version"])
    assert result.exit_code == 0
    assert "wzlcarrot" in result.output


def test_zhihu_platform_under_wzlcarrot():
    result = runner.invoke(root_app, ["zhihu", "--help"])
    assert result.exit_code == 0
    assert "hot" in result.output


def test_zhihu_alias_still_works():
    result = runner.invoke(app, ["hot", "--help"])
    assert result.exit_code == 0


def test_generic_commands_not_under_zhihu():
    # strict layering: generic commands live at the umbrella level only
    for args in (["zhihu", "version"], ["zhihu", "connect"], ["zhihu", "doctor"]):
        assert runner.invoke(root_app, args).exit_code != 0


def test_generic_commands_available_at_root():
    for args in (["plugins"], ["connect", "--list"], ["doctor", "--offline"], ["sessions"]):
        result = runner.invoke(root_app, args)
        assert result.exit_code == 0, (args, result.output)


def test_platform_commands_live_under_zhihu():
    # `hot` is not a root command; it lives under the `zhihu` group.
    assert runner.invoke(root_app, ["hot"]).exit_code != 0
    zhihu_help = runner.invoke(root_app, ["zhihu", "--help"]).output
    assert "hot" in zhihu_help and "comment" in zhihu_help

