"""Revision 0136: the database becomes ``runs.db`` — the four history tables
that pointed at ``resources.id`` are re-keyed to the resource's uid, every row
kept, and the tables whose state moved into files are dropped (ADR
storage-is-five-classes-by-nature)."""

from __future__ import annotations

import sqlite3

import pytest
from alembic import command

from coffer.infrastructure.vault.migration.errors import PreVaultDatabase
from coffer.surfaces.http import migrations_runner
from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
)

_DROPPED = {
    "resources",
    "secrets",
    "secret_bindings",
    "secret_approvals",
    "secret_boundary_settings",
    "mcp_capability_preferences",
    "channel_peers",
    "internal_engine_config",
    "retention_policies",
    "skill_source_status",
    "skill_agent_bindings",
    "mcp_server_health",
    "mcp_tool_reach",
    "sync_remotes",
    "sync_convergence_state",
    "sync_held_paths",
}


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _seed(conn: sqlite3.Connection) -> None:
    for rid, uid, kind, name in [
        (1, "uid-one", "channel", "tg"),
        (2, "uid-two", "mcp_server", "gh"),
    ]:
        conn.execute(
            "INSERT INTO resources (id, uid, kind, name, config_json, enabled, created_at,"
            " updated_at, rev) VALUES (?, ?, ?, ?, '{}', 1, '2026-09-01', '2026-09-01', 1)",
            (rid, uid, kind, name),
        )
    audit = [(1, 1), (2, 2), (3, None), (4, 99)]
    for aid, rid in audit:
        conn.execute(
            "INSERT INTO audit_log (id, timestamp, event_type, actor, resource_id, resource_kind,"
            " resource_name) VALUES (?, '2026-09-02', 'resource_updated', 'user', ?, 'k', 'n')",
            (aid, rid),
        )
    conn.execute(
        "INSERT INTO channel_thread_conversations (id, resource_id, chat_id, thread_id,"
        " updated_at, preferred_model) VALUES (5, 1, 'c1', '', '2026-09-02', 'm')"
    )
    conn.execute(
        "INSERT INTO channel_thread_history (id, resource_id, chat_id, thread_id,"
        " conversation_id, opened_at) VALUES (6, 1, 'c1', 't', 'conv-1', '2026-09-02')"
    )
    conn.execute(
        "INSERT INTO channel_outbox (id, resource_id, chat_id, thread_id, chat_kind,"
        " conversation_id, kind, text, created_at) VALUES (7, 1, 'c1', '', 'direct', 'conv-1',"
        " 'reply', 'hi', '2026-09-02')"
    )
    conn.execute(
        "INSERT INTO sync_runs (started_at, finished_at, status, payload_json)"
        " VALUES ('2026-09-02', '2026-09-02', 'ok', '{\"applied\": {}}')"
    )
    conn.commit()


def test_history_is_rekeyed_to_uids_and_every_row_is_kept(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "runs.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()
    command.upgrade(cfg, "0135")
    with sqlite3.connect(db_path) as conn:
        _seed(conn)
    command.upgrade(cfg, "0136")
    with sqlite3.connect(db_path) as conn:
        assert not (_tables(conn) & _DROPPED)
        assert conn.execute("SELECT id, resource_uid FROM audit_log ORDER BY id").fetchall() == [
            (1, "uid-one"),
            (2, "uid-two"),
            (3, None),
            (4, None),
        ]
        assert conn.execute(
            "SELECT id, resource_uid, chat_id, preferred_model FROM channel_thread_conversations"
        ).fetchall() == [(5, "uid-one", "c1", "m")]
        assert conn.execute(
            "SELECT id, resource_uid, conversation_id FROM channel_thread_history"
        ).fetchall() == [(6, "uid-one", "conv-1")]
        assert conn.execute("SELECT id, resource_uid, text FROM channel_outbox").fetchall() == [
            (7, "uid-one", "hi")
        ]
        for table in ("audit_log", "channel_outbox", "channel_thread_history"):
            columns = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            assert "resource_id" not in columns and "resource_uid" in columns
        indexes = {r[1] for r in conn.execute("PRAGMA index_list(audit_log)")}
        assert "idx_audit_resource_uid" in indexes
        # The old rounds' payloads do not parse as round records: they go,
        # the table stays for the thin sync's rounds.
        assert conn.execute("SELECT count(*) FROM sync_runs").fetchone() == (0,)
    command.downgrade(cfg, "0135")
    with sqlite3.connect(db_path) as conn:
        assert _tables(conn) >= _DROPPED
        assert conn.execute("SELECT count(*) FROM audit_log").fetchone() == (4,)


def test_the_runner_refuses_a_database_from_before_the_layout(  # type: ignore[no-untyped-def]
    tmp_path, monkeypatch
) -> None:
    """The daemon never moves the pre-vault tables out itself (that is
    ``coffer migrate``): upgrading such a database to head would drop them."""
    db_path = tmp_path / "runs.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    monkeypatch.setenv("COFFER_DB_URL", url)
    command.upgrade(_alembic_config(), "0110")
    with pytest.raises(PreVaultDatabase):
        migrations_runner.run_migrations(url)
    with sqlite3.connect(db_path) as conn:
        assert "resources" in _tables(conn)
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone() == ("0110",)


def test_a_fresh_database_goes_straight_to_head(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "runs.db"
    migrations_runner.run_migrations(f"sqlite+aiosqlite:///{db_path}")
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone() == ("0136",)
        assert "resources" not in _tables(conn)
