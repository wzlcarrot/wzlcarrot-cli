"""Credential storage and login helpers."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from http.cookies import CookieError, SimpleCookie

from .config import credentials_file


@dataclass
class Credentials:
    cookies: dict[str, str] = field(default_factory=dict)
    saved_at: float = 0.0

    @property
    def d_c0(self) -> str:
        return self.cookies.get("d_c0", "")

    @property
    def z_c0(self) -> str:
        return self.cookies.get("z_c0", "")

    def cookie_header(self) -> str:
        return "; ".join(f"{k}={v}" for k, v in self.cookies.items())

    def is_logged_in(self) -> bool:
        return bool(self.d_c0 and self.z_c0)

    def save(self) -> None:
        self.saved_at = time.time()
        path = credentials_file()
        plaintext = json.dumps(asdict(self), ensure_ascii=False)
        from .crypto import encrypt_text

        payload = {"version": 2, "encrypted": encrypt_text(plaintext)}
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        path.chmod(0o600)

    @classmethod
    def load(cls) -> Credentials:
        path = credentials_file()
        if not path.exists():
            return cls()
        # Defense in depth: re-tighten permissions in case something loosened them.
        try:
            path.chmod(0o600)
        except OSError:
            pass
        data = json.loads(path.read_text(encoding="utf-8"))
        if "encrypted" in data:  # v2 encrypted format
            from .crypto import decrypt_text

            try:
                data = json.loads(decrypt_text(str(data["encrypted"])))
            except Exception as exc:
                from .exceptions import ZhihuError

                raise ZhihuError(
                    "凭证解密失败（密钥丢失或文件损坏）：请重新运行 `zhihu login`"
                ) from exc
        return cls(cookies=data.get("cookies", {}), saved_at=data.get("saved_at", 0.0))

    @classmethod
    def from_cookie_string(cls, raw: str) -> Credentials:
        cookies: dict[str, str] = {}
        # Try the lenient parser first, then fall back to a manual split.
        jar: SimpleCookie = SimpleCookie()
        try:
            jar.load(raw)
            cookies = {k: m.value for k, m in jar.items()}
        except (CookieError, ValueError):
            cookies = {}
        if not cookies:
            for part in raw.split(";"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    cookies[k.strip()] = v.strip()
        if not cookies:
            raise ValueError("could not parse any cookie from the provided string")
        return cls(cookies=cookies)


def clear_credentials() -> bool:
    path = credentials_file()
    if path.exists():
        path.unlink()
        return True
    return False
