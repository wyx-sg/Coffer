"""When a Fernet token was encrypted, read without the key (spec vault-storage).

A Fernet token is ``version || timestamp || IV || ciphertext || HMAC``, and the
timestamp is cleartext: eight big-endian bytes of Unix seconds right after the
version byte. So a credential file under ``vault/secret/`` says when its
value was last set on a machine that cannot decrypt it — which is both the
credential store's ``updated_at`` (there is no other place to keep it once the
ciphertext is a file) and the order two machines' copies of one ref are
settled by (ADR secrets-cross-machines-only-as-ciphertext: the fresher encryption wins,
never a text merge).

It lives in the vault's domain rather than sync's because the store reads it
on every listing, sync or no sync.
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

    Surrounding whitespace (the credential file's trailing newline) is ignored.
    None rather than an exception: a blob that is not a well-formed token must
    still be placeable, and "unknown" is the truthful answer.
    """
    try:
        raw = base64.urlsafe_b64decode(blob.strip())
    except (ValueError, TypeError):
        return None
    if len(raw) < _HEADER or raw[0] != _VERSION:
        return None
    return int(struct.unpack(">Q", raw[1:_HEADER])[0])


def is_fresher(candidate: bytes, incumbent: bytes) -> bool:
    """Whether ``candidate`` was encrypted after ``incumbent``.

    Ties and unreadable headers answer False, so the incumbent is kept:
    keeping an equally old blob costs nothing, replacing a current secret with
    an indistinguishable one can orphan a working credential.
    """
    a, b = encrypted_at(candidate), encrypted_at(incumbent)
    if a is None or b is None:
        return False
    return a > b


__all__ = ["encrypted_at", "is_fresher"]
