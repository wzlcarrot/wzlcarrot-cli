from __future__ import annotations

import pytest
from typer.testing import CliRunner

from wzlcarrot_cli import commands, edgelogin
from wzlcarrot_cli.cli import app
from wzlcarrot_cli.session import Credentials

runner = CliRunner()


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIHU_CLI_HOME", str(tmp_path))
    monkeypatch.setenv("ZHIHU_CLI_NO_UPDATE_CHECK", "1")
    monkeypatch.setattr(
        commands.login, "_validate", lambda creds, **kw: {"name": "t", "url_token": "t"}
    )
    return tmp_path


def test_login_uses_edge(monkeypatch, _home):
    called = {}

    def fake_edge_login(**_kwargs):
        called["yes"] = True
        return Credentials(cookies={"d_c0": "a", "z_c0": "b"})

    monkeypatch.setattr(commands.login, "edge_login", fake_edge_login)
    result = runner.invoke(app, ["login"])
    assert result.exit_code == 0, result.output
    assert called.get("yes") is True
    assert (_home / "credentials.json").exists()


def test_login_only_has_edge_no_other_methods():
    for flag in ("--qr", "--link", "--edge", "--reuse", "--browser"):
        assert runner.invoke(app, ["login", flag]).exit_code != 0, flag


def test_edge_login_filters_zhihu_cookies(monkeypatch):
    payload = (
        '{"result": {"cookies": ['
        '{"name": "z_c0", "value": "Z", "domain": ".zhihu.com"},'
        '{"name": "other", "value": "x", "domain": ".example.com"}'
        "]}}"
    )
    monkeypatch.setattr(edgelogin, "_run_powershell", lambda *a, **k: payload)
    creds = edgelogin.edge_login()
    assert creds.z_c0 == "Z"
    assert "other" not in creds.cookies


def test_edge_login_reports_timeout(monkeypatch):
    monkeypatch.setattr(edgelogin, "_run_powershell", lambda *a, **k: "ERR:timeout")
    with pytest.raises(Exception, match="超时"):
        edgelogin.edge_login()
