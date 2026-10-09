"""Give ``runs.db``'s free pages back to the disk.

Retention deletes rows, and SQLite keeps the pages they lived on as free pages
inside the file rather than shrinking it, so a history database that has been
pruned for months is mostly empty space. After each retention pass the worker
calls :func:`reclaim_free_pages`, which rebuilds the file with ``VACUUM`` once
the free pages are both most of the file and worth a rewrite, and otherwise
does nothing (ADR audit-and-retention, "Reclaiming the space pruning frees").

The rebuild runs on its own short-lived connection in a worker thread, so the
daemon's async engine keeps serving: in WAL mode readers carry on while the
rebuild writes, and a writer waits on the busy timeout like any other.
"""

from __future__ import annotations

import logging
import pathlib
import sqlite3
from dataclasses import dataclass

#: Rebuild only when free pages are at least this share of the file...
RECLAIM_MIN_FREE_FRACTION = 0.5
#: ...and add up to at least this much, so a small database is never rewritten
#: for a few kilobytes.
RECLAIM_MIN_FREE_BYTES = 8 * 1024 * 1024

_BUSY_TIMEOUT_SECONDS = 5.0

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PageCounts:
    """What ``PRAGMA page_size``, ``page_count`` and ``freelist_count`` report."""

    page_size: int
    page_count: int
    freelist_count: int

    @property
    def free_bytes(self) -> int:
        return self.freelist_count * self.page_size

    @property
    def free_fraction(self) -> float:
        return self.freelist_count / self.page_count if self.page_count else 0.0


def page_counts(conn: sqlite3.Connection) -> PageCounts:
    def pragma(name: str) -> int:
        return int(conn.execute(f"PRAGMA {name}").fetchone()[0])

    return PageCounts(
        page_size=pragma("page_size"),
        page_count=pragma("page_count"),
        freelist_count=pragma("freelist_count"),
    )


def reclaim_free_pages(
    db_path: pathlib.Path | None,
    *,
    min_free_fraction: float = RECLAIM_MIN_FREE_FRACTION,
    min_free_bytes: int = RECLAIM_MIN_FREE_BYTES,
) -> int:
    """``VACUUM`` the database when its free pages pass both thresholds, then
    truncate the WAL the rebuild went through. Returns the bytes the file
    shrank by; 0 when nothing was due or there is no file (an in-memory or
    not-yet-created database)."""
    if db_path is None or not db_path.is_file():
        return 0
    conn = sqlite3.connect(db_path, timeout=_BUSY_TIMEOUT_SECONDS, isolation_level=None)
    try:
        before = page_counts(conn)
        if before.free_fraction < min_free_fraction or before.free_bytes < min_free_bytes:
            return 0
        conn.execute("VACUUM")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        after = page_counts(conn)
    finally:
        conn.close()
    freed = max(0, (before.page_count - after.page_count) * before.page_size)
    _logger.info(
        "runs_db.vacuumed",
        extra={
            "freed_bytes": freed,
            "pages_before": before.page_count,
            "pages_after": after.page_count,
        },
    )
    return freed


__all__ = [
    "RECLAIM_MIN_FREE_BYTES",
    "RECLAIM_MIN_FREE_FRACTION",
    "PageCounts",
    "page_counts",
    "reclaim_free_pages",
]
