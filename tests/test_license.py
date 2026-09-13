from __future__ import annotations

import base64
import json
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from wzlcarrot_cli import license as lic
from wzlcarrot_cli.exceptions import ZhihuError


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIHU_CLI_HOME", str(tmp_path))
    monkeypatch.delenv(lic.LICENSE_ENV, raising=False)
    return tmp_path


def _sign(payload: dict) -> tuple[str, str]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    payload_b64 = base64.b64encode(json.dumps(payload).encode()).decode()
    signature = base64.b64encode(private.sign(payload_b64.encode())).decode()
    key = json.dumps({"payload": payload_b64, "signature": signature})
    return base64.b64encode(public).decode(), key


def test_free_by_default(home, monkeypatch):
    monkeypatch.delenv(lic.PUBKEY_ENV, raising=False)
    assert lic.current_status().is_pro is False
    assert lic.is_pro() is False


def test_activate_valid_license(home, monkeypatch):
    pub, key = _sign({"email": "a@b.c", "tier": "pro"})
    monkeypatch.setenv(lic.PUBKEY_ENV, pub)
    info = lic.activate(key)
    assert info.is_pro is True
    assert info.email == "a@b.c"
    assert lic.is_pro() is True
    assert lic.license_file().exists()


def test_tampered_payload_rejected(home, monkeypatch):
    pub, key = _sign({"tier": "pro"})
    monkeypatch.setenv(lic.PUBKEY_ENV, pub)
    data = json.loads(key)
    data["payload"] = base64.b64encode(b'{"tier":"pro"}').decode()  # different payload
    with pytest.raises(ZhihuError, match="无效"):
        lic.activate(json.dumps(data))


def test_expired_license_is_not_pro(home, monkeypatch):
    pub, key = _sign({"tier": "pro", "expires": time.time() - 10})
    monkeypatch.setenv(lic.PUBKEY_ENV, pub)
    monkeypatch.setenv(lic.LICENSE_ENV, key)
    assert lic.is_pro() is False


def test_no_public_key_cannot_verify(home, monkeypatch):
    monkeypatch.delenv(lic.PUBKEY_ENV, raising=False)
    _pub, key = _sign({"tier": "pro"})
    monkeypatch.setenv(lic.LICENSE_ENV, key)
    assert lic.is_pro() is False


def test_require_pro_raises_for_free(home, monkeypatch):
    monkeypatch.delenv(lic.PUBKEY_ENV, raising=False)
    with pytest.raises(ZhihuError, match="Pro"):
        lic.require_pro("批量导出")
