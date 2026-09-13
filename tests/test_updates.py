from __future__ import annotations

import json

import pytest

from zhihu_cli import updates, upgrade
from zhihu_cli.exceptions import ZhihuError


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIHU_CLI_HOME", str(tmp_path))
    return tmp_path


def test_parse_version_ordering():
    assert updates.parse_version("0.10.0") > updates.parse_version("0.9.0")
    assert updates.parse_version("1.0.0") > updates.parse_version("0.99.99")
    assert updates.parse_version("0.18.0b1") == updates.parse_version("0.18.0")


def test_check_disabled_by_env(home, monkeypatch):
    monkeypatch.setenv(updates.NO_CHECK_ENV, "1")

    def boom(timeout=2.0):
        raise AssertionError("must not hit the network")

    monkeypatch.setattr(updates, "fetch_latest_version", boom)
    assert updates.check_for_update("0.17.3") is None


def test_check_returns_newer_version_and_caches(home, monkeypatch):
    monkeypatch.setattr(updates, "fetch_latest_version", lambda timeout=2.0: "0.18.0")
    assert updates.check_for_update("0.17.3") == "0.18.0"
    cache = json.loads((home / "update_check.json").read_text())
    assert cache["latest"] == "0.18.0"

    # Fresh cache: no second network call even if PyPI is unreachable.
    def boom(timeout=2.0):
        raise AssertionError("cache should be used")

    monkeypatch.setattr(updates, "fetch_latest_version", boom)
    assert updates.check_for_update("0.17.3") == "0.18.0"


def test_check_none_when_up_to_date(home, monkeypatch):
    monkeypatch.setattr(updates, "fetch_latest_version", lambda timeout=2.0: "0.17.3")
    assert updates.check_for_update("0.17.3") is None


def test_check_survives_network_failure(home, monkeypatch):
    def fail(timeout=2.0):
        return None

    monkeypatch.setattr(updates, "fetch_latest_version", fail)
    assert updates.check_for_update("0.17.3") is None
    assert not (home / "update_check.json").exists()


def test_check_uses_cache_only_within_ttl(home, monkeypatch):
    monkeypatch.setattr(updates, "fetch_latest_version", lambda timeout=2.0: "0.18.0")
    assert updates.check_for_update("0.17.3", now=1000.0) == "0.18.0"

    # Same "now" one day later: cache expired, next call must hit the network.
    def fail(timeout=2.0):
        return None

    monkeypatch.setattr(updates, "fetch_latest_version", fail)
    assert updates.check_for_update("0.17.3", now=1000.0 + updates.CHECK_INTERVAL + 1) is None


class _Proc:
    def __init__(self, stdout: str, returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode


def test_detect_upgrade_command_prefers_uv(monkeypatch):
    monkeypatch.setattr(upgrade, "_run", lambda cmd, timeout=15.0: _Proc("zhihu-cli v0.17.3"))
    assert upgrade.detect_upgrade_command() == ["uv", "tool", "upgrade", "zhihu-cli"]


def test_detect_upgrade_command_falls_back_to_pipx(monkeypatch):
    def fake_run(cmd, timeout=15.0):
        if cmd[0] == "uv":
            return _Proc("warning: no tools installed", returncode=0)
        if cmd[0] == "pipx":
            return _Proc("tools include zhihu-cli 0.17.3")
        return None

    monkeypatch.setattr(upgrade, "_run", fake_run)
    assert upgrade.detect_upgrade_command() == ["pipx", "upgrade", "zhihu-cli"]


def test_upgrade_rejects_editable_install(monkeypatch):
    monkeypatch.setattr(upgrade, "is_editable_install", lambda: True)
    with pytest.raises(ZhihuError, match="editable"):
        upgrade.upgrade(assume_yes=True)


def test_upgrade_runs_detected_command(monkeypatch):
    monkeypatch.setattr(upgrade, "is_editable_install", lambda: False)
    monkeypatch.setattr(upgrade, "detect_upgrade_command", lambda: ["uv", "tool", "upgrade", "zhihu-cli"])
    ran = {}

    def fake_run(cmd):
        ran["cmd"] = cmd
        return _Proc("", returncode=0)

    monkeypatch.setattr(upgrade.subprocess, "run", fake_run)
    assert upgrade.upgrade(assume_yes=True) == 0
    assert ran["cmd"] == ["uv", "tool", "upgrade", "zhihu-cli"]
