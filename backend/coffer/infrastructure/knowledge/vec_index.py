"""sqlite-vec vector index — the ONLY importer of ``sqlite_vec``.

Loads the sqlite-vec extension on a raw sqlite3 connection and runs a per-store
KNN. The extension load is lazy and degrades gracefully: if the library or the
native extension is unavailable, ``available()`` returns False and the caller
(the index) skips vector mode (vector→keyword fallback).

Each store gets its OWN sqlite-vec virtual table, named by ``kind`` +
``resource_name`` (sanitized) and created at that store's embedding width. This
keeps stores isolated: two stores with different ``dimensions`` coexist, a
``knn`` query only ever touches its own store's table (no cross-store leak or
under-retrieval), and a width change rebuilds only that one store's table.

This module talks to a *synchronous* sqlite3 connection it opens itself against
the same DB file, because loadable extensions are not exposed through the async
SQLAlchemy/aiosqlite layer. All calls run in a worker thread.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import sqlite3
import struct
from collections.abc import Sequence

# Identifier-safe characters for a sqlite table name component.
_TABLE_SAFE = re.compile(r"[^A-Za-z0-9_]")


def _serialize(vector: Sequence[float]) -> bytes:
    """Pack a float vector into sqlite-vec's little-endian float32 blob."""
    return struct.pack(f"<{len(vector)}f", *vector)


def _store_table_name(kind: str, resource_name: str) -> str:
    """Derive a stable, collision-free sqlite table name for one store.

    The human-readable ``kind``/``resource_name`` are sanitized to identifier
    chars for readability, and a short hash of the *raw* pair is appended so two
    distinct stores can never collide after sanitization (e.g. ``a/b`` vs
    ``a_b``).
    """
    digest = hashlib.sha1(f"{kind}\x00{resource_name}".encode()).hexdigest()[:12]
    safe_kind = _TABLE_SAFE.sub("_", kind)[:24]
    safe_res = _TABLE_SAFE.sub("_", resource_name)[:48]
    return f"vec_chunks_{safe_kind}_{safe_res}_{digest}"


class VecIndex:
    """Per-store vector index keyed on the sqlite-vec extension.

    One instance is bound to a single ``(kind, resource_name)`` store and owns
    exactly one virtual table at ``dimensions`` width.
    """

    def __init__(self, db_path: str, dimensions: int, *, kind: str, resource_name: str) -> None:
        self._db_path = db_path
        self._dimensions = dimensions
        self._kind = kind
        self._resource = resource_name
        self._table = _store_table_name(kind, resource_name)
        self._available: bool | None = None

    @property
    def table(self) -> str:
        """The per-store virtual-table name (identifier-safe)."""
        return self._table

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.enable_load_extension(True)
        import sqlite_vec

        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return conn

    def available(self) -> bool:
        """Whether the sqlite-vec extension can be loaded (cached)."""
        if self._available is not None:
            return self._available
        try:
            conn = self._connect()
            conn.close()
            self._available = True
        except Exception:
            self._available = False
        return self._available

    def _current_width(self, conn: sqlite3.Connection) -> int | None:
        """The embedding width of the existing store table, or None if absent.

        Parsed from the stored ``CREATE`` SQL (``embedding FLOAT[<n>]``); sqlite-vec
        does not expose the width via ``PRAGMA table_info``.
        """
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (self._table,),
        ).fetchone()
        if not row or not row[0]:
            return None
        m = re.search(r"FLOAT\[(\d+)\]", str(row[0]))
        return int(m.group(1)) if m else None

    def _ensure(self, conn: sqlite3.Connection) -> None:
        """Create the per-store table at the configured width, rebuilding it if a
        prior table exists at a DIFFERENT width (a model/config change)."""
        width = self._current_width(conn)
        if width is not None and width != self._dimensions:
            conn.execute(f'DROP TABLE IF EXISTS "{self._table}"')
            width = None
        if width is None:
            conn.execute(
                f'CREATE VIRTUAL TABLE IF NOT EXISTS "{self._table}" '
                f"USING vec0(chunk_id TEXT PRIMARY KEY, embedding FLOAT[{self._dimensions}])"
            )

    def ensure_table(self) -> None:
        """Create (or rebuild on width change) this store's virtual table."""
        conn = self._connect()
        try:
            self._ensure(conn)
            conn.commit()
        finally:
            conn.close()

    async def upsert(self, rows: Sequence[tuple[str, Sequence[float]]]) -> None:
        if not rows:
            return

        def _run() -> None:
            conn = self._connect()
            try:
                self._ensure(conn)
                for chunk_id, vector in rows:
                    conn.execute(f'DELETE FROM "{self._table}" WHERE chunk_id = ?', (chunk_id,))
                    conn.execute(
                        f'INSERT INTO "{self._table}"(chunk_id, embedding) VALUES (?, ?)',
                        (chunk_id, _serialize(vector)),
                    )
                conn.commit()
            finally:
                conn.close()

        await asyncio.to_thread(_run)

    async def delete(self, chunk_ids: Sequence[str]) -> None:
        if not chunk_ids:
            return

        def _run() -> None:
            conn = self._connect()
            try:
                self._ensure(conn)
                conn.executemany(
                    f'DELETE FROM "{self._table}" WHERE chunk_id = ?',
                    [(cid,) for cid in chunk_ids],
                )
                conn.commit()
            finally:
                conn.close()

        await asyncio.to_thread(_run)

    async def drop(self) -> None:
        """Drop this store's entire vector table (store cleanup)."""

        def _run() -> None:
            conn = self._connect()
            try:
                conn.execute(f'DROP TABLE IF EXISTS "{self._table}"')
                conn.commit()
            finally:
                conn.close()

        await asyncio.to_thread(_run)

    async def knn(self, vector: Sequence[float], top_k: int) -> list[tuple[str, float]]:
        """Return ``[(chunk_id, distance), ...]`` nearest the query vector,
        scoped to THIS store's table only."""

        def _run() -> list[tuple[str, float]]:
            conn = self._connect()
            try:
                self._ensure(conn)
                # Use the ``k = ?`` constraint (not ``LIMIT``) for the KNN: it is
                # a virtual-table constraint sqlite-vec always sees, whereas a
                # ``LIMIT`` only reaches vec0 if the host sqlite pushes it down —
                # which some builds (notably the Linux CI sqlite) do not, raising
                # "a LIMIT or 'k = ?' constraint is required on vec0 knn queries".
                cur = conn.execute(
                    f'SELECT chunk_id, distance FROM "{self._table}" '
                    "WHERE embedding MATCH ? AND k = ? ORDER BY distance",
                    (_serialize(vector), top_k),
                )
                return [(str(cid), float(dist)) for cid, dist in cur.fetchall()]
            finally:
                conn.close()

        return await asyncio.to_thread(_run)
