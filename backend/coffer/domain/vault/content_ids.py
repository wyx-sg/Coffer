"""The two content ids the vault uses, computed without git.

- The **blob id** is git's own object id for a file's bytes, so a file's id
  here is the id ``git ls-tree`` reports for it: what the deletion breaker
  pairs moves by, what a writer compares against ``HEAD``, and what the
  resource revision counter watches.
- The **fingerprint** is a SHA-256 of the bytes, the value every content API
  already takes as ``expected_fingerprint``: a writer states the fingerprint
  of what it read, and a mismatch is a stale write (409), never a silent
  overwrite.

Both are pure functions of the bytes — never of a path, a modification time
or anything else a checkout, a backup tool or a clock can change.
"""

from __future__ import annotations

import hashlib

#: git's hash of the zero-byte blob.
EMPTY_BLOB = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"


def blob_id(data: bytes) -> str:
    """git's object id for a blob holding ``data``."""
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()


def fingerprint(data: bytes) -> str:
    """SHA-256 hex of ``data`` — the expected-content token of every write."""
    return hashlib.sha256(data).hexdigest()


__all__ = ["EMPTY_BLOB", "blob_id", "fingerprint"]
