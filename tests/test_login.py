from __future__ import annotations

import pytest
from typer.testing import CliRunner

from wzlcarrot_cli import commands
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


def _fake_qr_login(captured):
    def fake(*, show_qr: bool = False, **_kwargs):
        captured["show_qr"] = show_qr
        return Credentials(cookies={"d_c0": "a", "z_c0": "b"})

    return fake


def test_login_defaults_to_link_flow(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(commands.login, "qr_login", _fake_qr_login(captured))
    result = runner.invoke(app, ["login"])
    assert result.exit_code == 0, result.output
    assert captured["show_qr"] is False  # default: link, no QR


def test_login_qr_flag_requests_qr(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(commands.login, "qr_login", _fake_qr_login(captured))
    result = runner.invoke(app, ["login", "--qr"])
    assert result.exit_code == 0, result.output
    assert captured["show_qr"] is True


def test_login_with_cookie_skips_link_flow(monkeypatch):
    def boom(**_kwargs):
        raise AssertionError("cookie login must not call the link flow")

    monkeypatch.setattr(commands.login, "qr_login", boom)
    result = runner.invoke(app, ["login", "--cookie", "d_c0=a; z_c0=b"])
    assert result.exit_code == 0, result.output
