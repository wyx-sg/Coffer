"""Startup guard: refuse a DB whose Alembic revision this build doesn't know.

When a DB was migrated by a newer/divergent Coffer build (its revision isn't
in this build's migration tree), ``upgrade head`` would raise an opaque
"Can't locate revision identified by ..." and the daemon would die during
lifespan startup. ``_guard_schema_not_newer`` turns that into a clear
``DatabaseSchemaTooNew`` with an actionable message.
"""

from __future__ import annotations

import pathlib
import sqlite3

import pytest

from coffer.domain.errors import DatabaseSchemaTooNew
from coffer.surfaces.http.migrations_runner import _alembic_config, _guard_schema_not_newer

HEAD_REVISION = "0013"  # mirrors test_migrations_roundtrip.HEAD_REVISION


def _stamp(db_path: pathlib.Path, revision: str) -> None:
    """Create a minimal alembic_version table stamped at ``revision``."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES (?)", (revision,))
        conn.commit()
    finally:
        conn.close()


def _point_db_at(monkeypatch: pytest.MonkeyPatch, db_path: pathlib.Path) -> None:
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")


def test_future_revision_raises(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "coffer.db"
    _stamp(db, "9999")  # a revision this build's migration tree does not contain
    _point_db_at(monkeypatch, db)

    with pytest.raises(DatabaseSchemaTooNew) as exc:
        _guard_schema_not_newer(_alembic_config(), f"sqlite+aiosqlite:///{db}")
    assert exc.value.current == "9999"
    assert str(db) in str(exc.value)


def test_known_head_revision_passes(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "coffer.db"
    _stamp(db, HEAD_REVISION)  # a revision this build knows
    _point_db_at(monkeypatch, db)

    # Must not raise — head is a known revision.
    _guard_schema_not_newer(_alembic_config(), f"sqlite+aiosqlite:///{db}")


def test_fresh_db_passes(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "coffer.db"
    db.touch()  # empty DB: no alembic_version table → current revision is None
    _point_db_at(monkeypatch, db)

    # Must not raise — a fresh DB migrates cleanly from base.
    _guard_schema_not_newer(_alembic_config(), f"sqlite+aiosqlite:///{db}")
