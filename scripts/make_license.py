#!/usr/bin/env python3
"""Issue Ed25519 license keys (vendor-side tool).

    # one-time: create an issuer keypair (keep the private key secret)
    python scripts/make_license.py keygen --out issuer

    # embed the printed public key as DEFAULT_PUBKEY in wzlcarrot_cli/license.py

    # issue a license for a customer
    python scripts/make_license.py sign --key issuer.key --email a@b.c --tier pro --days 365
"""

from __future__ import annotations

import argparse
import base64
import json
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def keygen(out: str) -> None:
    private = Ed25519PrivateKey.generate()
    Path(f"{out}.key").write_bytes(
        private.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
    )
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    Path(f"{out}.pub").write_text(base64.b64encode(public).decode(), encoding="utf-8")
    print(f"private key: {out}.key (keep secret)")
    print(f"public key (embed as DEFAULT_PUBKEY): {base64.b64encode(public).decode()}")


def sign(key_path: str, email: str, tier: str, days: int) -> None:
    private = Ed25519PrivateKey.from_private_bytes(Path(key_path).read_bytes())
    payload: dict = {"email": email, "tier": tier, "issued": int(time.time())}
    if days > 0:
        payload["expires"] = int(time.time()) + days * 86400
    payload_b64 = base64.b64encode(json.dumps(payload).encode()).decode()
    signature = base64.b64encode(private.sign(payload_b64.encode())).decode()
    print(json.dumps({"payload": payload_b64, "signature": signature}))


def main() -> None:
    parser = argparse.ArgumentParser(description="Issue wzlcarrot-cli licenses")
    sub = parser.add_subparsers(dest="cmd", required=True)

    kg = sub.add_parser("keygen")
    kg.add_argument("--out", default="issuer")

    sg = sub.add_parser("sign")
    sg.add_argument("--key", required=True, help="private key file")
    sg.add_argument("--email", required=True)
    sg.add_argument("--tier", default="pro")
    sg.add_argument("--days", type=int, default=365, help="0 = perpetual")

    args = parser.parse_args()
    if args.cmd == "keygen":
        keygen(args.out)
    else:
        sign(args.key, args.email, args.tier, args.days)


if __name__ == "__main__":
    main()
