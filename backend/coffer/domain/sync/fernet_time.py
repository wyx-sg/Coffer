"""Freshness ordering for credential ciphertext (spec 010).

A Fernet token embeds its encryption epoch in cleartext (byte 0 is the
version marker ``0x80``, bytes 1-9 a big-endian u64), so two blobs for the
same ref can be ordered without any key — which keeps the sync engine's
"never touches plaintext" invariant while letting it refuse to replace a
newer encryption with an older one (the 2026-07-10 stale-clobber incident).
"""

from __future__ import annotations

import base64
import binascii

_VERSION = 0x80
_HEADER_LEN = 9


def fernet_created_at(blob: bytes) -> int | None:
    """Encryption epoch embedded in a Fernet token, or None when unparseable.

    None (rather than an exception) keeps callers on their existing
    last-writer-wins behavior for anything that is not a well-formed token.
    """
    try:
        raw = base64.urlsafe_b64decode(blob.strip())
    except (binascii.Error, ValueError):
        return None
    if len(raw) < _HEADER_LEN or raw[0] != _VERSION:
        return None
    return int.from_bytes(raw[1:_HEADER_LEN], "big")


def is_staler(candidate: bytes, existing: bytes) -> bool:
    """True when ``candidate`` is a strictly older encryption than ``existing``.

    Unknown timestamps on either side compare as "not staler", preserving the
    pre-guard overwrite semantics for malformed blobs.
    """
    candidate_ts = fernet_created_at(candidate)
    existing_ts = fernet_created_at(existing)
    return candidate_ts is not None and existing_ts is not None and candidate_ts < existing_ts
