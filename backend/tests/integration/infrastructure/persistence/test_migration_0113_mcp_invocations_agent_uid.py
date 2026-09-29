"""Revision 0113: ``mcp_invocations`` gains a nullable ``agent_uid`` column and
its ``(agent_uid, timestamp)`` index (spec mcp-gateway "Record invocations
without content"). A row written before the revision keeps reading and names
no agent; the downgrade drops the column and the index again.

Reuses the alembic driving helpers from the round-trip suite so this speaks to
the real migration scripts.
"""

from __future__ import annotations

import sqlite3

from alembic import command

from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
)

_TABLE = "mcp_invocations"
_INDEX = "idx_invocations_agent"


def _columns(conn: sqlite3.Connection) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({_TABLE})")}


def _indexes(conn: sqlite3.Connection) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA index_list({_TABLE})")}


def test_agent_uid_is_added_null_for_old_rows_and_dropped_on_downgrade(  # type: ignore[no-untyped-def]
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "invocations.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()
    command.upgrade(cfg, "0112")
    with sqlite3.connect(db_path) as conn:
        assert "agent_uid" not in _columns(conn)
        conn.execute(
            f"INSERT INTO {_TABLE} (timestamp, resource_uid, capability_type, capability_key,"
            " duration_ms, status, session_id) VALUES ('2026-09-29 00:00:00', 'u1', 'tool',"
            " 'read_file', 3, 'ok', 's1')"
        )
        conn.commit()

    command.upgrade(cfg, "0113")
    with sqlite3.connect(db_path) as conn:
        assert "agent_uid" in _columns(conn)
        assert _INDEX in _indexes(conn)
        rows = conn.execute(f"SELECT capability_key, agent_uid FROM {_TABLE}").fetchall()
        assert rows == [("read_file", None)]

    command.downgrade(cfg, "0112")
    with sqlite3.connect(db_path) as conn:
        assert "agent_uid" not in _columns(conn)
        assert _INDEX not in _indexes(conn)
        assert conn.execute(f"SELECT capability_key FROM {_TABLE}").fetchall() == [("read_file",)]
