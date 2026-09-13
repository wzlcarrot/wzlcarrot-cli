from __future__ import annotations

import pytest
from typer.testing import CliRunner

from zhihu_cli.cli import app, root_app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _no_update_check(monkeypatch):
    monkeypatch.setenv("ZHIHU_CLI_NO_UPDATE_CHECK", "1")


def test_root_version():
    result = runner.invoke(root_app, ["version"])
    assert result.exit_code == 0
    assert "wzlcarrot" in result.output


def test_zhihu_platform_under_wzlcarrot():
    result = runner.invoke(root_app, ["zhihu", "version"])
    assert result.exit_code == 0
    assert "0.18" in result.output


def test_zhihu_alias_still_works():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.18" in result.output
