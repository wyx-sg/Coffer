"""Revision 0104: a direct chat's thread row can say it is a parallel thread.

``channel_thread_conversations`` gains ``parallel_ordinal`` and
``parallel_title`` (spec channels "Open parallel conversations in a direct
chat"). Existing rows are left without an ordinal — which is what folds the
casual direct-chat threads recorded before into the direct chat's conversation —
and the downgrade drops both columns again.

Reuses the alembic driving helpers from the round-trip suite so this speaks to
the real migration scripts.
"""

from __future__ import annotations

import sqlite3

from alembic import command

from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
)

_TABLE = "channel_thread_conversations"


def _columns(conn: sqlite3.Connection) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({_TABLE})")}


def _upgrade(tmp_path, monkeypatch, revision: str):  # type: ignore[no-untyped-def]
    db_path = tmp_path / "parallel.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()
    command.upgrade(cfg, revision)
    return db_path, cfg


def test_existing_thread_rows_gain_empty_parallel_columns(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    db_path, cfg = _upgrade(tmp_path, monkeypatch, "0103")
    with sqlite3.connect(db_path) as conn:
        assert not {"parallel_ordinal", "parallel_title"} & _columns(conn)
        conn.execute(
            "INSERT INTO resources (id, uid, kind, name, config_json, enabled, created_at,"
            " updated_at) VALUES (1, 'u1', 'channel', 'st', '{}', 1,"
            " '2026-09-28 00:00:00', '2026-09-28 00:00:00')"
        )
        conn.execute(
            f"INSERT INTO {_TABLE} (resource_id, chat_id, thread_id, active_conversation_id,"
            " preferred_agent, updated_at) VALUES (1, 'emp-1', 'm-root', 'c1', NULL,"
            " '2026-09-28 00:00:00')"
        )
        conn.commit()

    command.upgrade(cfg, "0104")

    with sqlite3.connect(db_path) as conn:
        assert {"parallel_ordinal", "parallel_title"} <= _columns(conn)
        assert conn.execute(
            f"SELECT thread_id, active_conversation_id, parallel_ordinal, parallel_title"
            f" FROM {_TABLE}"
        ).fetchall() == [("m-root", "c1", None, None)]


def test_downgrading_0104_drops_the_parallel_columns(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    db_path, cfg = _upgrade(tmp_path, monkeypatch, "0104")
    command.downgrade(cfg, "0103")
    with sqlite3.connect(db_path) as conn:
        assert not {"parallel_ordinal", "parallel_title"} & _columns(conn)
