from __future__ import annotations

import stat

from zhihu_cli.config import credentials_file
from zhihu_cli.session import Credentials


def test_save_sets_owner_only_permissions(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIHU_CLI_HOME", str(tmp_path))
    Credentials(cookies={"d_c0": "d", "z_c0": "z"}).save()
    mode = stat.S_IMODE(credentials_file().stat().st_mode)
    assert mode == 0o600


def test_load_tightens_loosened_permissions(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIHU_CLI_HOME", str(tmp_path))
    Credentials(cookies={"d_c0": "d", "z_c0": "z"}).save()
    path = credentials_file()
    path.chmod(0o644)  # something loosened it
    Credentials.load()
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600
