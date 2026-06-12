"""Identifier helpers for the substrate.

- ``new_ulid()`` mints a Crockford-base32 ULID (lexicographically sortable, time
  + randomness) without a third-party dependency — used for memory fact ids.
- ``slugify()`` turns a fact ``name`` into a filesystem-safe ``<slug>.md`` stem.
"""

from __future__ import annotations

import os
import re
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def _encode(value: int, length: int) -> str:
    out = ["0"] * length
    for i in range(length - 1, -1, -1):
        out[i] = _CROCKFORD[value & 0x1F]
        value >>= 5
    return "".join(out)


def new_ulid() -> str:
    """A 26-char Crockford-base32 ULID (48-bit ms timestamp + 80-bit random)."""
    ms = int(time.time() * 1000)
    rand = int.from_bytes(os.urandom(10), "big")
    return _encode(ms, 10) + _encode(rand, 16)


def slugify(name: str, *, max_len: int = 64) -> str:
    """Filesystem-safe slug for a fact name; falls back to ``fact`` if empty."""
    slug = _SLUG_STRIP.sub("-", name.strip().lower()).strip("-")
    slug = slug[:max_len].strip("-")
    return slug or "fact"
