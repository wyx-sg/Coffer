"""Order two Fernet ciphertexts without holding the key (spec vault-sync).

A Fernet token is ``version || timestamp || IV || ciphertext || HMAC``, and the
timestamp is **cleartext** — eight big-endian bytes of Unix seconds right after
the version byte. So two blobs encrypting the same credential can be ordered by
when they were encrypted, on a machine that cannot decrypt either of them.

That is the whole reason this module exists. A credential blob is one line of
base64; when two machines re-encrypt the same ref, git has nothing to merge and
every text-level rule ("newest commit wins") picks by when a machine happened to
sync rather than by which secret is current. The 2026-07-10 incident was exactly
that: a machine re-exporting a months-old orphaned blob won the merge by syncing
last.

This comparator applies to ``credentials/*.enc`` and to nothing else. It was
written once for continuous sync, removed with it, and is restored unchanged in
scope: a general "newest wins" resolver is what the previous design's
auto-resolve grew into, and it grew bugs with it.
"""

from __future__ import annotations

import base64
import struct

#: Fernet's only defined version byte.
_VERSION = 0x80
#: version (1) + timestamp (8)
_HEADER = 9


def encrypted_at(blob: bytes) -> int | None:
    """Unix seconds a Fernet token was encrypted at, or None if it is not one.

    Returns None rather than raising: a blob that is not a well-formed token is
    something the caller must still be able to place, and "unknown" is a
    truthful answer that a caller can treat as "do not use this comparator".
    """
    try:
        raw = base64.urlsafe_b64decode(blob)
    except (ValueError, TypeError):
        return None
    if len(raw) < _HEADER or raw[0] != _VERSION:
        return None
    return int(struct.unpack(">Q", raw[1:_HEADER])[0])


def is_fresher(candidate: bytes, incumbent: bytes) -> bool:
    """Whether ``candidate`` was encrypted after ``incumbent``.

    Ties and unreadable headers answer False, so the incumbent is kept. The
    conservative direction is deliberate: keeping a blob that is merely
    equally-old costs nothing, while replacing a current secret with an
    indistinguishable one can orphan a working credential.
    """
    a, b = encrypted_at(candidate), encrypted_at(incumbent)
    if a is None or b is None:
        return False
    return a > b
