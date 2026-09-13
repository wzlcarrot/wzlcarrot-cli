"""Offline license keys and free/pro tiers.

A license is a small JSON object ``{"payload": <b64>, "signature": <b64>}``
where ``payload`` base64-decodes to ``{"email", "tier", "expires"?}`` and
``signature`` is an Ed25519 signature over the ``payload`` string.  Verification
uses an embedded issuer public key (or ``WZLCARROT_LICENSE_PUBKEY``), so a
license can be validated fully offline and cannot be forged without the private
key.  No phone-home.

The free tier is fully usable; Pro unlocks bulk operations.
"""

from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from .config import config_dir
from .exceptions import ZhihuError

FREE = "free"
PRO = "pro"

LICENSE_ENV = "WZLCARROT_LICENSE"
PUBKEY_ENV = "WZLCARROT_LICENSE_PUBKEY"
# Issuer public key (base64, 32 raw bytes). Fill this in before shipping Pro.
DEFAULT_PUBKEY = ""


def license_file() -> Path:
    return config_dir() / "license.key"


def _public_key_bytes() -> bytes | None:
    encoded = os.environ.get(PUBKEY_ENV) or DEFAULT_PUBKEY
    if not encoded:
        return None
    try:
        return base64.b64decode(encoded)
    except (ValueError, TypeError):
        return None


@dataclass
class Status:
    tier: str = FREE
    email: str = ""
    expires: float | None = None
    valid: bool = False

    @property
    def is_pro(self) -> bool:
        return self.valid and self.tier == PRO


def verify(payload_b64: str, signature_b64: str) -> dict | None:
    """Return the payload dict if the signature is valid, else ``None``."""
    public = _public_key_bytes()
    if public is None:
        return None
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        Ed25519PublicKey.from_public_bytes(public).verify(
            base64.b64decode(signature_b64), payload_b64.encode("ascii")
        )
    except (InvalidSignature, ValueError, TypeError):
        return None
    try:
        return json.loads(base64.b64decode(payload_b64))
    except (ValueError, TypeError):
        return None


def _read_raw() -> str | None:
    override = os.environ.get(LICENSE_ENV)
    if override:
        return override
    path = license_file()
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def current_status() -> Status:
    raw = _read_raw()
    if not raw:
        return Status()
    try:
        data = json.loads(raw)
        payload = verify(str(data["payload"]), str(data["signature"]))
    except (ValueError, KeyError, TypeError):
        return Status()
    if not payload:
        return Status()
    expires = payload.get("expires")
    status = Status(
        tier=str(payload.get("tier", PRO)),
        email=str(payload.get("email", "")),
        expires=float(expires) if expires else None,
        valid=True,
    )
    if status.expires and time.time() > status.expires:
        status.valid = False
    return status


def is_pro() -> bool:
    return current_status().is_pro


def activate(raw: str) -> Status:
    try:
        data = json.loads(raw)
        payload = verify(str(data["payload"]), str(data["signature"]))
    except (ValueError, KeyError, TypeError) as exc:
        raise ZhihuError("License 格式错误") from exc
    if not payload:
        raise ZhihuError("License 无效或签名校验失败")
    path = license_file()
    path.write_text(raw, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return current_status()


def deactivate() -> bool:
    path = license_file()
    if path.exists():
        path.unlink()
        return True
    return False


def require_pro(feature: str) -> None:
    if not is_pro():
        raise ZhihuError(
            f"「{feature}」是 Pro 功能。运行 `wzlcarrot license activate <key>` 激活后可用。"
        )
