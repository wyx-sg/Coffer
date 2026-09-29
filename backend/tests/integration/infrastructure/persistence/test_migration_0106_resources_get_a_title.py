"""Revision 0106: every resource may carry a display title.

A nullable column with no backfill: an existing row keeps everything it had and
has no title, and the downgrade takes the column away without touching a row.

Reuses the alembic driving helpers from the round-trip suite so this speaks to
the real migration scripts.
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


def test_0106_adds_a_nullable_title_and_keeps_every_row(tmp_path, monkeypatch):
    db_path = tmp_path / "title.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()
    command.upgrade(cfg, "0105")
    uid = uuid.uuid4().hex
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO resources (uid, kind, name, description, config_json, enabled,"
            " created_at, updated_at) VALUES (?, 'mcp_server', 'a-server-name-thirty-chars-xx',"
            " 'desc', '{}', 1, '2026-09-01', '2026-09-01')",
            (uid,),
        )
    assert "title" not in _columns(db_path)

    command.upgrade(cfg, "0106")

    assert _alembic_version(db_path) == "0106"
    assert _columns(db_path)["title"] == "VARCHAR(80)"
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT uid, name, description, title FROM resources WHERE uid = ?", (uid,)
        ).fetchone()
    # The row — including a name longer than the new 24-character cap for a
    # NEW server — is exactly as it was, with no title.
    assert row == (uid, "a-server-name-thirty-chars-xx", "desc", None)

    command.downgrade(cfg, "0105")
    assert "title" not in _columns(db_path)
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT name FROM resources WHERE uid = ?", (uid,)).fetchone() == (
            "a-server-name-thirty-chars-xx",
        )
