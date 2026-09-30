"""Revision 0199: ``mcp_server`` configs lose ``idle_timeout_seconds``.

``MCPServerConfig`` refuses keys it does not declare, so the retired key is
stripped from every stored ``mcp_server`` row. Everything else in the config,
and every other kind's row, is left as it was, and a row that is not a JSON
object never fails the upgrade.

Reuses the alembic driving helpers from the round-trip suite so this speaks to
the real migration scripts.
"""

from __future__ import annotations

import json
import sqlite3
import uuid

from alembic import command

from coffer.domain.mcp.server_config import MCPServerConfig
from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
    _alembic_version,
)

_STALE = {
    "transport": {"type": "stdio", "command": "x", "args": ["--y"]},
    "spawn_timeout_seconds": 45,
    "idle_timeout_seconds": 600,
}


def _insert(conn: sqlite3.Connection, kind: str, name: str, config_json: str) -> str:
    uid = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO resources (uid, kind, name, description, config_json, enabled,"
        " created_at, updated_at) VALUES (?, ?, ?, NULL, ?, 1, '2026-09-01', '2026-09-01')",
        (uid, kind, name, config_json),
    )
    return uid


def _config(db_path, uid: str) -> str:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT config_json FROM resources WHERE uid = ?", (uid,)).fetchone()
    return row[0]  # type: ignore[no-any-return]


def test_0199_strips_the_retired_key_from_mcp_server_rows_only(tmp_path, monkeypatch):
    db_path = tmp_path / "mcp.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()
    command.upgrade(cfg, "0135")
    other = json.dumps({"idle_timeout_seconds": 600})
    with sqlite3.connect(db_path) as conn:
        stale = _insert(conn, "mcp_server", "fs", json.dumps(_STALE))
        clean_json = json.dumps({"transport": {"type": "stdio", "command": "z"}})
        clean = _insert(conn, "mcp_server", "clean", clean_json)
        unreadable = _insert(conn, "mcp_server", "broken", "not json")
        not_an_object = _insert(conn, "mcp_server", "listy", "[1, 2]")
        foreign = _insert(conn, "channel", "chan", other)

    command.upgrade(cfg, "0199")

    assert _alembic_version(db_path) == "0199"
    stripped = json.loads(_config(db_path, stale))
    assert stripped == {
        "transport": {"type": "stdio", "command": "x", "args": ["--y"]},
        "spawn_timeout_seconds": 45,
    }
    # The stripped row now loads under the model that refuses unknown keys.
    MCPServerConfig.model_validate(stripped)
    assert _config(db_path, clean) == clean_json
    assert _config(db_path, unreadable) == "not json"
    assert _config(db_path, not_an_object) == "[1, 2]"
    assert _config(db_path, foreign) == other

    command.downgrade(cfg, "0135")
    assert json.loads(_config(db_path, stale)) == stripped
