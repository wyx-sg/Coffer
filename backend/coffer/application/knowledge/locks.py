"""Per-store async locks serializing substrate write operations.

The reconcile/index pipeline runs on every read and write; two concurrent
operations on one store (an agent recall racing a UI edit, two recalls after an
out-of-band fact edit) would interleave their delete/insert batches and
duplicate embedding work. One process-local lock per ``(kind, resource_name)``
serializes the logical operation; the single-transaction ``upsert_chunks``
holds the row-level invariants underneath.

Process-local is sufficient: the daemon is the only writer of ``coffer.db``.
"""

from __future__ import annotations

import asyncio


class StoreLocks:
    """A lazily-populated ``asyncio.Lock`` per ``(kind, resource_name)``."""

    def __init__(self) -> None:
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    def lock(self, kind: str, resource_name: str) -> asyncio.Lock:
        key = (kind, resource_name)
        lock = self._locks.get(key)
        if lock is None:
            # setdefault keeps the first lock if two callers race the miss.
            lock = self._locks.setdefault(key, asyncio.Lock())
        return lock
