"""Revision 0102: ``conversations.agent_key`` stops defaulting to ``builtin``.

0012 created the column with ``server_default='builtin'``, back when a built-in
chat persona existed. That persona is gone, so a writer that forgets to name the
agent must be refused by the store rather than silently routed to an agent that
no longer exists. 0102 drops the default and leaves every existing row as it was.

Reuses the alembic driving helpers from the round-trip suite so this speaks to
the real migration scripts.
"""

from __future__ import annotations

import sqlite3

import pytest
from alembic import command

from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
)


def _agent_key_default(conn: sqlite3.Connection) -> object:
    for _cid, name, _type, _notnull, default, _pk in conn.execute(
        "PRAGMA table_info(conversations)"
    ):
        if name == "agent_key":
            return default
    raise AssertionError("conversations.agent_key is missing")


def _upgrade(tmp_path, monkeypatch, revision: str):
    db_path = tmp_path / "agent_key.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()
    command.upgrade(cfg, revision)
    return db_path, cfg


def test_a_conversation_without_an_agent_is_refused_by_the_store_at_head(tmp_path, monkeypatch):
    db_path, _cfg = _upgrade(tmp_path, monkeypatch, "head")
    with sqlite3.connect(db_path) as conn:
        assert _agent_key_default(conn) is None
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at)"
                " VALUES ('c1', 't', '2026-09-23 00:00:00', '2026-09-23 00:00:00')"
            )


def test_dropping_the_default_leaves_existing_conversations_untouched(tmp_path, monkeypatch):
    db_path, cfg = _upgrade(tmp_path, monkeypatch, "0101")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO conversations (id, agent_key, title, created_at, updated_at,"
            " archived_at, agent_config, channel_uid, peer_chat_id, owner)"
            " VALUES ('c1', 'claude_code', 'hello', '2026-09-23 00:00:00',"
            " '2026-09-23 01:00:00', NULL, '{\"model\": \"m\"}', 'ch', 'peer', 'me')"
        )
        conn.execute(
            "INSERT INTO chat_messages (id, conversation_id, seq, role, content, created_at)"
            " VALUES ('m1', 'c1', 1, 'user', 'hi', '2026-09-23 00:00:00')"
        )
        conn.commit()
        before = conn.execute("SELECT * FROM conversations").fetchall()
        indexes_before = sorted(
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='conversations'"
                " AND name NOT LIKE 'sqlite_%'"
            )
        )

    command.upgrade(cfg, "0102")

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT * FROM conversations").fetchall() == before
        assert conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone() == (1,)
        indexes_after = sorted(
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='conversations'"
                " AND name NOT LIKE 'sqlite_%'"
            )
        )
        assert indexes_after == indexes_before


def test_downgrading_0102_restores_the_old_default(tmp_path, monkeypatch):
    db_path, cfg = _upgrade(tmp_path, monkeypatch, "0102")
    command.downgrade(cfg, "0101")
    with sqlite3.connect(db_path) as conn:
        assert _agent_key_default(conn) == "'builtin'"
