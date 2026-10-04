"""Revision 0107: every resource carries a monotonic revision.

Existing rows start at 1, and the downgrade takes the column away without
touching a row.
"""

from __future__ import annotations

import sqlite3
import uuid

from alembic import command

from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
    _alembic_version,
)


def _columns(db_path) -> dict[str, str]:
    with sqlite3.connect(db_path) as conn:
        return {row[1]: row[2] for row in conn.execute("PRAGMA table_info(resources)")}


def test_0107_adds_a_rev_starting_at_one_and_keeps_every_row(tmp_path, monkeypatch):
    db_path = tmp_path / "rev.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()
    command.upgrade(cfg, "0106")
    uid = uuid.uuid4().hex
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO resources (uid, kind, name, description, config_json, enabled,"
            " created_at, updated_at) VALUES (?, 'skill', 'a-skill', 'desc', '{}', 1,"
            " '2026-09-01', '2026-09-01')",
            (uid,),
        )
    assert "rev" not in _columns(db_path)

    command.upgrade(cfg, "0107")

    assert _alembic_version(db_path) == "0107"
    assert _columns(db_path)["rev"] == "INTEGER"
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT uid, name, description, rev FROM resources WHERE uid = ?", (uid,)
        ).fetchone()
    assert row == (uid, "a-skill", "desc", 1)

    command.downgrade(cfg, "0106")
    assert "rev" not in _columns(db_path)
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT name FROM resources WHERE uid = ?", (uid,)).fetchone() == (
            "a-skill",
        )
