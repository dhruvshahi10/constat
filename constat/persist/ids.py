"""ULIDs with the stdlib: 48 bits of milliseconds, 80 bits of randomness,
Crockford base32. Sortable by creation time, safe in URLs, no dependency."""
from __future__ import annotations

import secrets
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode(value: int, length: int) -> str:
    out = []
    for _ in range(length):
        out.append(_ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(out))


def ulid(ts_ms: int | None = None) -> str:
    ts = int(time.time() * 1000) if ts_ms is None else ts_ms
    return _encode(ts, 10) + _encode(secrets.randbits(80), 16)
