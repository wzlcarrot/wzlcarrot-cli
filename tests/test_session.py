from __future__ import annotations

import stat

from wzlcarrot_cli.config import credentials_file
from wzlcarrot_cli.session import Credentials


def test_save_sets_owner_only_permissions(tmp_path, monkeypatch):
    monkeypatch.setenv("WZLCARROT_CLI_HOME", str(tmp_path))
    Credentials(cookies={"d_c0": "d", "z_c0": "z"}).save()
    mode = stat.S_IMODE(credentials_file().stat().st_mode)
    assert mode == 0o600


def test_load_tightens_loosened_permissions(tmp_path, monkeypatch):
    monkeypatch.setenv("WZLCARROT_CLI_HOME", str(tmp_path))
    Credentials(cookies={"d_c0": "d", "z_c0": "z"}).save()
    path = credentials_file()
    path.chmod(0o644)  # something loosened it
    Credentials.load()
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600


def test_save_encrypts_at_rest(tmp_path, monkeypatch):
    monkeypatch.setenv("WZLCARROT_CLI_HOME", str(tmp_path))
    from wzlcarrot_cli.session import Credentials

    Credentials(cookies={"d_c0": "secret-dc0", "z_c0": "secret-zc0"}).save()
    raw = (tmp_path / "credentials.json").read_text(encoding="utf-8")
    assert "secret-dc0" not in raw and "secret-zc0" not in raw  # not plaintext
    assert '"encrypted"' in raw

    loaded = Credentials.load()
    assert loaded.d_c0 == "secret-dc0"
    assert loaded.is_logged_in()


def test_load_legacy_plaintext(tmp_path, monkeypatch):
    monkeypatch.setenv("WZLCARROT_CLI_HOME", str(tmp_path))
    import json

    from wzlcarrot_cli.session import Credentials

    (tmp_path / "credentials.json").write_text(
        json.dumps({"cookies": {"d_c0": "legacy", "z_c0": "legacy-z"}, "saved_at": 1.0}),
        encoding="utf-8",
    )
    loaded = Credentials.load()
    assert loaded.d_c0 == "legacy"


def test_corrupt_ciphertext_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("WZLCARROT_CLI_HOME", str(tmp_path))
    import json

    import pytest

    from wzlcarrot_cli.exceptions import ZhihuError
    from wzlcarrot_cli.session import Credentials

    (tmp_path / "credentials.json").write_text(
        json.dumps({"version": 2, "encrypted": "not-a-valid-token"}), encoding="utf-8"
    )
    with pytest.raises(ZhihuError, match="解密失败"):
        Credentials.load()
