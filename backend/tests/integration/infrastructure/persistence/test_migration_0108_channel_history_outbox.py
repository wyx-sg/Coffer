"""Revision 0108: channel threads keep their settings, remember their
conversations, and hold the web's undelivered replies.

``channel_thread_conversations`` gains ``chat_kind`` and the sticky
``preferred_model`` / ``preferred_effort`` / ``preferred_cwd``;
``channel_thread_history`` is created and back-filled with each thread's
current conversation (one row per conversation), so it can be resumed and
mirrored from the start; ``channel_outbox`` is created empty (spec chat "Mirror
a web reply into the channel it came from"). The downgrade drops all of it.

Reuses the alembic driving helpers from the round-trip suite so this speaks to
the real migration scripts.
"""

from __future__ import annotations

import sqlite3

from alembic import command

from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
)

_THREADS = "channel_thread_conversations"
_NEW_COLUMNS = {"chat_kind", "preferred_model", "preferred_effort", "preferred_cwd"}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _upgrade(tmp_path, monkeypatch, revision: str):  # type: ignore[no-untyped-def]
    db_path = tmp_path / "history.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()
    command.upgrade(cfg, revision)
    return db_path, cfg


def _thread(conn: sqlite3.Connection, chat: str, thread: str, conv: str | None, at: str) -> None:
    conn.execute(
        f"INSERT INTO {_THREADS} (resource_id, chat_id, thread_id, active_conversation_id,"
        " preferred_agent, updated_at) VALUES (1, ?, ?, ?, NULL, ?)",
        (chat, thread, conv, at),
    )


def test_each_active_conversation_is_back_filled_once(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    db_path, cfg = _upgrade(tmp_path, monkeypatch, "0107")
    with sqlite3.connect(db_path) as conn:
        assert "channel_thread_history" not in _tables(conn)
        conn.execute(
            "INSERT INTO resources (id, uid, kind, name, config_json, enabled, created_at,"
            " updated_at) VALUES (1, 'u1', 'channel', 'st', '{}', 1,"
            " '2026-09-28 00:00:00', '2026-09-28 00:00:00')"
        )
        _thread(conn, "emp-1", "", "c1", "2026-09-28 01:00:00")
        _thread(conn, "grp-1", "t-1", "c2", "2026-09-28 02:00:00")
        # The same conversation reached from two rows yields one history row.
        _thread(conn, "grp-1", "t-2", "c2", "2026-09-28 03:00:00")
        # A thread with no conversation has no history.
        _thread(conn, "emp-2", "", None, "2026-09-28 04:00:00")
        conn.commit()

    command.upgrade(cfg, "0108")

    with sqlite3.connect(db_path) as conn:
        assert _columns(conn, _THREADS) >= _NEW_COLUMNS
        assert {"channel_thread_history", "channel_outbox"} <= _tables(conn)
        rows = conn.execute(
            "SELECT resource_id, chat_id, thread_id, conversation_id, chat_kind"
            " FROM channel_thread_history ORDER BY conversation_id"
        ).fetchall()
        assert rows == [(1, "emp-1", "", "c1", None), (1, "grp-1", "t-1", "c2", None)]
        assert conn.execute("SELECT COUNT(*) FROM channel_outbox").fetchone() == (0,)


def test_downgrading_0108_drops_the_tables_and_columns(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    db_path, cfg = _upgrade(tmp_path, monkeypatch, "0108")
    command.downgrade(cfg, "0107")
    with sqlite3.connect(db_path) as conn:
        assert not {"channel_thread_history", "channel_outbox"} & _tables(conn)
        assert not _NEW_COLUMNS & _columns(conn, _THREADS)
