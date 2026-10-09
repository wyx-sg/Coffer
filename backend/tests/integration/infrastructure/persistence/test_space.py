"""runs.db gives the pages pruning freed back to the disk once they are most of
the file, and leaves a file that is mostly data alone."""

from __future__ import annotations

import pathlib
import sqlite3

import pytest

from coffer.infrastructure.persistence.space import page_counts, reclaim_free_pages


def _pruned_db(db: pathlib.Path, *, rows: int, keep: int) -> None:
    """A WAL-mode file that held ``rows`` rows of ~4 KB and kept ``keep``."""
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("CREATE TABLE audit_log (id INTEGER PRIMARY KEY, body TEXT)")
    conn.executemany("INSERT INTO audit_log (body) VALUES (?)", [("x" * 4000,)] * rows)
    conn.execute("DELETE FROM audit_log WHERE id > ?", (keep,))
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()


def _counts(db: pathlib.Path):
    conn = sqlite3.connect(db)
    try:
        return page_counts(conn)
    finally:
        conn.close()


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a prune that leaves runs.db mostly empty shrinks the file"
)
def test_a_mostly_free_file_is_rebuilt_and_keeps_its_rows(tmp_path: pathlib.Path) -> None:
    db = tmp_path / "runs.db"
    _pruned_db(db, rows=3000, keep=10)
    before = _counts(db)
    assert before.free_fraction > 0.9

    freed = reclaim_free_pages(db)

    after = _counts(db)
    assert freed == (before.page_count - after.page_count) * before.page_size
    assert freed > 8 * 1024 * 1024
    assert after.freelist_count == 0
    assert db.stat().st_size == after.page_count * after.page_size
    assert not (tmp_path / "runs.db-wal").exists() or (tmp_path / "runs.db-wal").stat().st_size == 0
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone() == (10,)
    finally:
        conn.close()


def test_a_file_that_is_mostly_data_is_left_alone(tmp_path: pathlib.Path) -> None:
    db = tmp_path / "runs.db"
    _pruned_db(db, rows=3000, keep=2000)
    before = _counts(db)

    assert reclaim_free_pages(db) == 0
    assert _counts(db) == before


def test_a_small_file_is_not_rewritten_for_a_few_pages(tmp_path: pathlib.Path) -> None:
    """Most of it is free, but too little in bytes to be worth a rewrite."""
    db = tmp_path / "runs.db"
    _pruned_db(db, rows=100, keep=1)
    before = _counts(db)
    assert before.free_fraction > 0.5

    assert reclaim_free_pages(db) == 0
    assert _counts(db) == before


def test_no_file_means_nothing_to_reclaim(tmp_path: pathlib.Path) -> None:
    assert reclaim_free_pages(None) == 0
    assert reclaim_free_pages(tmp_path / "missing.db") == 0
    assert not (tmp_path / "missing.db").exists()
