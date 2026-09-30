"""Revision 0133: knowledge collections lose their titles; other kinds keep theirs
(spec resource-framework "Carry an optional editable title on the kinds that
have one")."""

from __future__ import annotations

import json
import sqlite3
import uuid

from alembic import command

from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
)


def _insert(conn: sqlite3.Connection, *, kind: str, name: str, title: str | None) -> str:
    uid = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO resources (uid, kind, name, description, config_json, enabled,"
        " created_at, updated_at, scope_json, title, rev)"
        " VALUES (?, ?, ?, NULL, ?, 1, '2026-09-01', '2026-09-01', NULL, ?, 1)",
        (uid, kind, name, json.dumps({}), title),
    )
    return uid


def test_0133_clears_collection_titles_and_keeps_the_rest(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    db = tmp_path / "c.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db}")
    command.upgrade(_alembic_config(), "0115")
    with sqlite3.connect(db) as conn:
        collection = _insert(conn, kind="knowledge", name="shopee", title="Shopee notes")
        partition = _insert(conn, kind="memory", name="coffer", title="Coffer memory")

    command.upgrade(_alembic_config(), "0133")

    with sqlite3.connect(db) as conn:
        titles = dict(conn.execute("SELECT uid, title FROM resources").fetchall())
    assert titles[collection] is None
    assert titles[partition] == "Coffer memory"
