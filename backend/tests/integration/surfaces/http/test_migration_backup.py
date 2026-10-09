"""The database is copied aside before a schema upgrade actually runs.

A migration that fails half-way, or whose data rewrite is wrong, used to be
unrecoverable — the daemon's only copy of the vault was the one being changed.
``run_migrations`` now leaves ``runs.db.pre-<revision>`` beside it whenever an
upgrade is due — one compact file written with ``VACUUM INTO`` — keeps the
newest three, and does nothing when the schema is
already current or the URL is not a file.
"""

from __future__ import annotations

import os
import pathlib
import sqlite3

import pytest

from coffer.infrastructure.persistence.migrations_runner import (
    KEEP_PRE_MIGRATION_COPIES,
    backup_before_migrate,
    run_migrations,
    sqlite_file,
)
from tests.integration.infrastructure.persistence.test_migrations_roundtrip import HEAD_REVISION


def _url(db: pathlib.Path) -> str:
    return f"sqlite+aiosqlite:///{db}"


@pytest.fixture(autouse=True)
def _never_the_real_vault(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """Alembic's env.py reads COFFER_DB_URL and falls back to ~/.coffer/runs.db
    when it is unset — ``run_migrations`` would otherwise upgrade the developer's
    real vault. Every test here pins the variable; the ones that migrate set it
    to the file they migrate."""
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'unused.db'}")


def _migrate(monkeypatch: pytest.MonkeyPatch, url: str) -> pathlib.Path | None:
    monkeypatch.setenv("COFFER_DB_URL", url)
    return run_migrations(url)


def _revision(db: pathlib.Path) -> str:
    conn = sqlite3.connect(db)
    try:
        return str(conn.execute("SELECT version_num FROM alembic_version").fetchone()[0])
    finally:
        conn.close()


def test_sqlite_file_identifies_only_existing_on_disk_databases(tmp_path: pathlib.Path) -> None:
    db = tmp_path / "runs.db"
    assert sqlite_file(_url(db)) is None, "a file that does not exist yet has nothing to copy"
    db.touch()
    assert sqlite_file(_url(db)) == db
    assert sqlite_file("sqlite+aiosqlite:///:memory:") is None
    assert sqlite_file("sqlite+aiosqlite://") is None
    assert sqlite_file("sqlite+aiosqlite:///file:x?mode=memory&cache=shared") is None
    assert sqlite_file("postgresql+asyncpg://u@h/db") is None
    assert sqlite_file("not a url at all ::") is None


@pytest.mark.acceptance(
    spec="daemon", scenario="a schema upgrade keeps a copy of the history database"
)
def test_upgrade_from_a_fresh_file_leaves_a_pre_migration_copy(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "runs.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE marker (x INTEGER)")
    conn.execute("INSERT INTO marker VALUES (42)")
    conn.commit()
    conn.close()

    backup = _migrate(monkeypatch, _url(db))

    assert backup == tmp_path / "runs.db.pre-base"
    assert backup.is_file()
    assert _revision(db) == HEAD_REVISION
    # The copy is the state from BEFORE the upgrade: the marker row is there
    # and no alembic_version table is.
    copy = sqlite3.connect(backup)
    try:
        assert copy.execute("SELECT x FROM marker").fetchone() == (42,)
        tables = {r[0] for r in copy.execute("SELECT name FROM sqlite_master")}
        assert "alembic_version" not in tables
    finally:
        copy.close()


def test_no_copy_when_the_schema_is_already_current(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The normal restart: nothing is due, so nothing is copied."""
    db = tmp_path / "runs.db"
    db.touch()
    assert _migrate(monkeypatch, _url(db)) is not None
    before = sorted(p.name for p in tmp_path.iterdir())

    assert _migrate(monkeypatch, _url(db)) is None
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_in_memory_url_is_migrated_without_a_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _migrate(monkeypatch, "sqlite+aiosqlite:///:memory:") is None


def _db_with(db: pathlib.Path, value: int) -> None:
    """A real SQLite file holding one marker row, in WAL mode like runs.db."""
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("CREATE TABLE IF NOT EXISTS marker (x INTEGER)")
    conn.execute("DELETE FROM marker")
    conn.execute("INSERT INTO marker VALUES (?)", (value,))
    conn.commit()
    conn.close()


def _marker(db: pathlib.Path) -> int:
    conn = sqlite3.connect(db)
    try:
        return int(conn.execute("SELECT x FROM marker").fetchone()[0])
    finally:
        conn.close()


def test_backup_is_one_compact_file_that_includes_what_the_wal_holds(
    tmp_path: pathlib.Path,
) -> None:
    """``VACUUM INTO`` reads through the WAL and writes live pages only: the
    copy needs no companions, and the free pages a prune left are not in it."""
    db = tmp_path / "runs.db"
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA wal_autocheckpoint = 0")  # keep the rows below in the WAL
    conn.execute("CREATE TABLE history (body TEXT)")
    conn.executemany("INSERT INTO history VALUES (?)", [("x" * 4000,)] * 500)
    conn.execute("DELETE FROM history WHERE rowid > 1")  # what a retention prune does
    conn.commit()
    assert (tmp_path / "runs.db-wal").stat().st_size > 0

    dest = backup_before_migrate(db, "0042")
    conn.close()

    assert dest == tmp_path / "runs.db.pre-0042"
    assert not (tmp_path / "runs.db.pre-0042-wal").exists()
    assert not (tmp_path / "runs.db.pre-0042-shm").exists()
    copy = sqlite3.connect(dest)
    try:
        assert copy.execute("SELECT COUNT(*) FROM history").fetchone() == (1,)
        assert copy.execute("PRAGMA freelist_count").fetchone() == (0,)
    finally:
        copy.close()
    assert dest.stat().st_size < 64 * 1024


def test_backup_never_overwrites_an_earlier_copy_of_the_same_revision(
    tmp_path: pathlib.Path,
) -> None:
    """The earlier copy is the state before the FIRST attempt — the one to keep
    if that attempt left the live file half-migrated."""
    db = tmp_path / "runs.db"
    _db_with(db, 1)
    first = backup_before_migrate(db, "0042")
    _db_with(db, 2)

    second = backup_before_migrate(db, "0042")

    assert _marker(first) == 1
    assert second == tmp_path / "runs.db.pre-0042.1"
    assert _marker(second) == 2


def test_only_the_newest_copies_are_kept(tmp_path: pathlib.Path) -> None:
    db = tmp_path / "runs.db"
    _db_with(db, 7)
    for i, rev in enumerate(("0001", "0002", "0003", "0004")):
        stale = tmp_path / f"runs.db.pre-{rev}"
        stale.write_bytes(b"old")
        # Copies an earlier build took carry companions.
        (tmp_path / f"runs.db.pre-{rev}-wal").write_bytes(b"old")
        os.utime(stale, (1_000_000 + i, 1_000_000 + i))

    backup_before_migrate(db, "0005")

    copies = sorted(p.name for p in tmp_path.glob("runs.db.pre-*") if "-wal" not in p.name)
    assert len(copies) == KEEP_PRE_MIGRATION_COPIES
    assert copies == ["runs.db.pre-0003", "runs.db.pre-0004", "runs.db.pre-0005"]
    # A pruned copy takes its companions with it; a kept one keeps them.
    assert not (tmp_path / "runs.db.pre-0001-wal").exists()
    assert (tmp_path / "runs.db.pre-0004-wal").exists()
    assert _marker(db) == 7


def test_a_failed_copy_leaves_nothing_behind(tmp_path: pathlib.Path) -> None:
    db = tmp_path / "runs.db"
    db.write_bytes(b"not a database at all, and longer than a header" * 4)

    with pytest.raises(sqlite3.DatabaseError):
        backup_before_migrate(db, "0042")

    assert not (tmp_path / "runs.db.pre-0042").exists()
