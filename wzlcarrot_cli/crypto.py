"""At-rest encryption for stored credentials.

Credentials are encrypted with Fernet.  The key is stored in a private (0600)
key file next to the config so it is identical across every interpreter that
reads the same config directory.  This protects against casual reads and
accidental commits; a determined local attacker with read access to the config
directory can still recover it.
"""

from __future__ import annotations

from pathlib import Path

from .config import config_dir


def key_file() -> Path:
    return config_dir() / ".credentials.key"


def _get_or_create_key() -> bytes:
    from cryptography.fernet import Fernet

    path = key_file()
    if path.exists():
        data = path.read_bytes().strip()
        if data:
            return data
    key = Fernet.generate_key()
    path.write_bytes(key)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return key


def encrypt_text(text: str) -> str:
    from cryptography.fernet import Fernet

    return Fernet(_get_or_create_key()).encrypt(text.encode("utf-8")).decode("ascii")


def decrypt_text(token: str) -> str:
    from cryptography.fernet import Fernet

    return Fernet(_get_or_create_key()).decrypt(token.encode("ascii")).decode("utf-8")
