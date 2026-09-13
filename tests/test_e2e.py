"""End-to-end CLI smoke tests (in-process, no network).

Exercises the real Typer entry points through CliRunner: the umbrella command,
the zhihu platform group, generic commands, license, and a full command path
with a mocked client.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from wzlcarrot_cli import commands
from wzlcarrot_cli.cli import app, root_app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _no_update(monkeypatch):
    monkeypatch.setenv("ZHIHU_CLI_NO_UPDATE_CHECK", "1")


def test_e2e_root_commands():
    for args in (
        ["version"],
        ["--help"],
        ["plugins"],
        ["hooks"],
        ["license", "status"],
        ["connect", "--list"],
    ):
        result = runner.invoke(root_app, args)
        assert result.exit_code == 0, (args, result.output)


def test_e2e_doctor_offline():
    result = runner.invoke(root_app, ["doctor", "--offline"])
    assert result.exit_code == 0
    assert "版本" in result.output


def test_e2e_zhihu_group_exposes_platform_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("hot", "search", "question", "answer", "article", "action", "publish", "download"):
        assert command in result.output


def test_e2e_hot_with_mocked_client(monkeypatch):
    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def hot_list(self, limit=50):
            return {
                "data": [
                    {
                        "target": {
                            "title": "端到端标题",
                            "url": "https://api.zhihu.com/questions/1",
                            "metricsArea": {"text": "100 万热度"},
                        }
                    }
                ]
            }

    monkeypatch.setattr(commands.feed, "require_client", lambda ctx: FakeClient())
    result = runner.invoke(app, ["hot", "-n", "1"])
    assert result.exit_code == 0, result.output
    assert "端到端标题" in result.output
