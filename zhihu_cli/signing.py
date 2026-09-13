"""Pure-Python implementation of Zhihu's ``x-zse-96`` v2 request signature.

The algorithm is a direct port of the reverse-engineered Rust signer from
``zly2006/zhihu-plus-plus`` (AGPL-3.0).  A widely used Python transcription
lives at ``Starzzb/zhihu-zse96-v2-python``.  It is isolated here on purpose:
Zhihu may rotate the scheme at any time, and this is the single module that
should need updating when it does.

Public API::

    sign_zse96(path_and_query, d_c0, body=None) -> "2.0_...."

``path_and_query`` must be the literal request target (path + ``?query``)
exactly as it is sent on the wire, otherwise the signature will not match.
"""

from __future__ import annotations

import hashlib
import struct

ZSE93 = "101_3_3.0"

_ZK = [
    1170614578, 1024848638, 1413669199, 3951632832, 3528873006, 2921909214,
    4151847688, 3997739139, 1933479194, 3323781115, 3888513386, 460404854,
    3747539722, 2403641034, 2615871395, 2119585428, 2265697227, 2035090028,
    2773447226, 4289380121, 4217216195, 2200601443, 3051914490, 1579901135,
    1321810770, 456816404, 2903323407, 4065664991, 330002838, 3506006750,
    363569021, 2347096187,
]

_ZB = [
    20, 223, 245, 7, 248, 2, 194, 209, 87, 6, 227, 253, 240, 128, 222, 91,
    237, 9, 125, 157, 230, 93, 252, 205, 90, 79, 144, 199, 159, 197, 186, 167,
    39, 37, 156, 198, 38, 42, 43, 168, 217, 153, 15, 103, 80, 189, 71, 191,
    97, 84, 247, 95, 36, 69, 14, 35, 12, 171, 28, 114, 178, 148, 86, 182,
    32, 83, 158, 109, 22, 255, 94, 238, 151, 85, 77, 124, 254, 18, 4, 26,
    123, 176, 232, 193, 131, 172, 143, 142, 150, 30, 10, 146, 162, 62, 224,
    218, 196, 229, 1, 192, 213, 27, 110, 56, 231, 180, 138, 107, 242, 187,
    54, 120, 19, 44, 117, 228, 215, 203, 53, 239, 251, 127, 81, 11, 133, 96,
    204, 132, 41, 115, 73, 55, 249, 147, 102, 48, 122, 145, 106, 118, 74,
    190, 29, 16, 174, 5, 177, 129, 63, 113, 99, 31, 161, 76, 246, 34, 211,
    13, 60, 68, 207, 160, 65, 111, 82, 165, 67, 169, 225, 57, 112, 244, 155,
    51, 236, 200, 233, 58, 61, 47, 100, 137, 185, 64, 17, 70, 234, 163, 219,
    108, 170, 166, 59, 149, 52, 105, 24, 212, 78, 173, 45, 0, 116, 226, 119,
    136, 206, 135, 175, 195, 25, 92, 121, 208, 126, 139, 3, 75, 141, 21, 130,
    98, 241, 40, 154, 66, 184, 49, 181, 46, 243, 88, 101, 183, 8, 23, 72,
    188, 104, 179, 210, 134, 250, 201, 164, 89, 216, 202, 220, 50, 221, 152,
    140, 33, 235, 214,
]

_ALPHABET = "6fpLRqJO8M/c3jnYxFkUVC4ZIG12SiH=5v0mXDazWBTsuw7QetbKdoPyAl+hN9rgE"
_KEY16 = b"059053f7d15e01d7"


def _uri_encode(s: str) -> bytes:
    """Mimic JavaScript ``encodeURIComponent`` semantics."""
    native = set(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.!~*'()")
    out = bytearray()
    for ch in s:
        b = ord(ch)
        if b in native:
            out.append(b)
        else:
            out.extend(f"%{b:02X}".encode())
    return bytes(out)


def _rotl(v: int, n: int) -> int:
    return ((v << n) | (v >> (32 - n))) & 0xFFFFFFFF


def _g_transform(tt: int) -> int:
    te = struct.pack(">I", tt & 0xFFFFFFFF)
    tr = bytes([_ZB[te[0]], _ZB[te[1]], _ZB[te[2]], _ZB[te[3]]])
    ti = struct.unpack(">I", tr)[0]
    return ti ^ _rotl(ti, 2) ^ _rotl(ti, 10) ^ _rotl(ti, 18) ^ _rotl(ti, 24)


def _r_block(block16: bytes) -> bytes:
    if len(block16) != 16:
        raise ValueError("r_block expects exactly 16 bytes")
    tr = [0] * 36
    tr[0] = struct.unpack(">I", block16[0:4])[0]
    tr[1] = struct.unpack(">I", block16[4:8])[0]
    tr[2] = struct.unpack(">I", block16[8:12])[0]
    tr[3] = struct.unpack(">I", block16[12:16])[0]
    for i in range(32):
        ta = _g_transform(tr[i + 1] ^ tr[i + 2] ^ tr[i + 3] ^ _ZK[i])
        tr[i + 4] = (tr[i] ^ ta) & 0xFFFFFFFF
    out = bytearray()
    for idx in (35, 34, 33, 32):
        out.extend(struct.pack(">I", tr[idx]))
    return bytes(out)


def _x_blocks(data: bytes, iv: bytes) -> bytes:
    out = bytearray()
    current_iv = bytearray(iv)
    for off in range(0, len(data), 16):
        chunk = data[off:off + 16]
        mixed = bytes([chunk[i] ^ current_iv[i] for i in range(len(chunk))])
        if len(mixed) < 16:
            mixed += b"\x00" * (16 - len(mixed))
        result = _r_block(mixed)
        out.extend(result)
        current_iv = bytearray(result)
    return bytes(out)


def _custom_encode(data: bytes) -> str:
    while len(data) % 3 != 0:
        data += b"\x00"
    out: list[str] = []
    p = len(data) - 1
    i = 0
    while p >= 0:
        v = 0
        v |= (data[p] ^ ((58 >> (8 * (i % 4))) & 0xFF)) & 0xFF
        i += 1
        v |= ((data[p - 1] ^ ((58 >> (8 * (i % 4))) & 0xFF)) & 0xFF) << 8
        i += 1
        v |= ((data[p - 2] ^ ((58 >> (8 * (i % 4))) & 0xFF)) & 0xFF) << 16
        i += 1
        out.append(_ALPHABET[v & 63])
        out.append(_ALPHABET[(v >> 6) & 63])
        out.append(_ALPHABET[(v >> 12) & 63])
        out.append(_ALPHABET[(v >> 18) & 63])
        p -= 3
    return "".join(out)


def _encrypt(input_str: str) -> str:
    seed = 12
    plain = bytearray()
    plain.append(seed)
    plain.append(0)
    plain.extend(_uri_encode(input_str))
    pad = 16 - (len(plain) % 16)
    plain.extend([pad] * pad)

    plain_bytes = bytes(plain)
    first = bytes([plain_bytes[i] ^ _KEY16[i] ^ 42 for i in range(16)])
    c0 = _r_block(first)
    cipher = bytearray(c0)
    if len(plain_bytes) > 16:
        cipher.extend(_x_blocks(plain_bytes[16:], c0))
    return _custom_encode(bytes(cipher))


def sign_zse96(path_and_query: str, d_c0: str, body: str | None = None) -> str:
    """Return the ``x-zse-96`` header value for a request.

    ``path_and_query`` should include the leading ``/`` and the exact query
    string, e.g. ``/api/v4/questions/123/answers?offset=0&limit=20``.
    """
    parts = [ZSE93, path_and_query, d_c0]
    if body:
        parts.append(body)
    source = "+".join(parts)
    md5_hex = hashlib.md5(source.encode("utf-8")).hexdigest()
    return f"2.0_{_encrypt(md5_hex)}"


if __name__ == "__main__":  # pragma: no cover - manual smoke check
    value = sign_zse96("/api/v4/me", "dummy_d_c0")
    assert value.startswith("2.0_"), value
    print(value)
