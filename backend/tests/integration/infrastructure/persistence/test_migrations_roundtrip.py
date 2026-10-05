"""The ``runs.db`` migration tree: one baseline, revisions stacked on it.

Drives the real migration scripts against a throwaway SQLite file:

* the baseline (``0146``) creates exactly the schema the full history it
  replaced left behind — ``old_chain_schema_0146.json`` is ``sqlite_master``
  as the 131-revision chain (``0001`` … ``0146``) wrote it, captured before
  that chain was squashed, so a database the old chain brought to ``0146``
  and one the baseline created are the same database;
* the tree has one base and one head, and the base is the baseline;
* ``upgrade head`` → ``downgrade base`` → ``upgrade head`` round-trips, so
  every revision stacked on the baseline must ship a working ``downgrade()``.

``env.py`` reads ``COFFER_DB_URL`` (an async ``sqlite+aiosqlite://`` URL) when
the Alembic config names no database, so the tests set it and let ``env.py``
do the async/sync conversion itself.
"""

from __future__ import annotations

import json
import pathlib
import re
import sqlite3

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory

#: The baseline revision: the id the squashed history ended at.
BASELINE_REVISION = "0146"
#: The newest revision in the tree. Equal to the baseline until a revision is
#: stacked on it; bump it with each new revision.
HEAD_REVISION = "0150"

_ALEMBIC_INI = (
    pathlib.Path(__file__).resolve().parents[4]
    / "coffer"
    / "infrastructure"
    / "persistence"
    / "migrations"
    / "alembic.ini"
)
_OLD_CHAIN_SCHEMA = pathlib.Path(__file__).with_name("old_chain_schema_0146.json")


def _alembic_config() -> AlembicConfig:
    assert _ALEMBIC_INI.is_file(), f"alembic.ini not found at {_ALEMBIC_INI}"
    return AlembicConfig(str(_ALEMBIC_INI))


def _normalized(sql: str | None) -> str | None:
    """``sqlite_master.sql`` with whitespace collapsed and identifier quotes
    dropped: a table the old chain rebuilt in batch mode is stored as
    ``CREATE TABLE "audit_log" (...)``, the same table created directly as
    ``CREATE TABLE audit_log (...)``, and SQLite treats the two alike."""
    if sql is None:
        return None
    return re.sub(r"\s+", " ", sql).replace('"', "").strip()


def _schema(db_path: pathlib.Path) -> list[tuple[str, str, str, str | None]]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT type, name, tbl_name, sql FROM sqlite_master").fetchall()
    return sorted((t, n, tb, _normalized(s)) for t, n, tb, s in rows if tb != "alembic_version")


def _alembic_version(db_path: pathlib.Path) -> str | None:
    with sqlite3.connect(db_path) as conn:
        try:
            row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        except sqlite3.OperationalError:
            return None
    return row[0] if row else None


def test_the_baseline_creates_the_schema_the_old_history_left(tmp_path, monkeypatch):
    db_path = tmp_path / "baseline.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")

    command.upgrade(_alembic_config(), BASELINE_REVISION)

    expected = sorted(
        (t, n, tb, _normalized(s)) for t, n, tb, s in json.loads(_OLD_CHAIN_SCHEMA.read_text())
    )
    assert _schema(db_path) == expected
    assert _alembic_version(db_path) == BASELINE_REVISION


@pytest.mark.acceptance(
    spec="chat", scenario="a conversation row with no agent is refused by the store"
)
def test_a_conversation_without_an_agent_is_refused_by_the_store(tmp_path, monkeypatch):
    db_path = tmp_path / "agentless.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    command.upgrade(_alembic_config(), "head")

    with sqlite3.connect(db_path) as conn:
        default = next(
            r[4] for r in conn.execute("PRAGMA table_info(conversations)") if r[1] == "agent_key"
        )
        assert default is None
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at)"
                " VALUES ('c1', 't', '2026-09-23 00:00:00', '2026-09-23 00:00:00')"
            )


def test_the_tree_is_one_line_from_the_baseline():
    script = ScriptDirectory.from_config(_alembic_config())
    assert script.get_bases() == [BASELINE_REVISION]
    assert script.get_heads() == [HEAD_REVISION]
    assert script.get_revision(BASELINE_REVISION).down_revision is None


def test_migration_roundtrip_is_reversible_and_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "roundtrip.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "head")
    at_head = _schema(db_path)
    assert at_head
    assert _alembic_version(db_path) == HEAD_REVISION

    command.downgrade(cfg, "base")
    assert _schema(db_path) == []
    assert _alembic_version(db_path) is None

    command.upgrade(cfg, "head")
    assert _schema(db_path) == at_head
    assert _alembic_version(db_path) == HEAD_REVISION


def test_0147_drops_the_effort_column_and_the_stored_effort_key(tmp_path, monkeypatch):
    db_path = tmp_path / "effort.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()
    command.upgrade(cfg, "0146")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO conversations (id, agent_key, title, created_at, updated_at, agent_config)"
            " VALUES ('c1', 'claude_code', 't', '2026-10-05 00:00:00', '2026-10-05 00:00:00',"
            ' \'{"cwd": "/tmp", "model": "opus", "effort": "high"}\')'
        )
        conn.execute(
            "INSERT INTO conversations (id, agent_key, title, created_at, updated_at)"
            " VALUES ('c2', 'claude_code', 't', '2026-10-05 00:00:00', '2026-10-05 00:00:00')"
        )

    command.upgrade(cfg, "0148")

    with sqlite3.connect(db_path) as conn:
        columns = [r[1] for r in conn.execute("PRAGMA table_info(channel_thread_conversations)")]
        assert "preferred_effort" not in columns
        stored = conn.execute("SELECT agent_config FROM conversations WHERE id='c1'").fetchone()[0]
        assert json.loads(stored) == {"cwd": "/tmp", "model": "opus"}
        assert (
            conn.execute("SELECT agent_config FROM conversations WHERE id='c2'").fetchone()[0]
            is None
        )


@pytest.mark.acceptance(
    spec="chat", scenario="the upgrade drops the text and keeps channel conversations"
)
def test_0149_drops_the_message_store_and_the_conversations_no_channel_owns(tmp_path, monkeypatch):
    db_path = tmp_path / "messages.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()
    command.upgrade(cfg, "0148")
    with sqlite3.connect(db_path) as conn:
        for cid, channel in (("web", None), ("chan", "ch-1")):
            conn.execute(
                "INSERT INTO conversations (id, agent_key, title, created_at, updated_at,"
                " channel_uid, peer_chat_id, archived_at)"
                " VALUES (?, 'claude_code', 't', '2026-10-05 00:00:00', '2026-10-05 00:00:00',"
                " ?, ?, '2026-10-05 00:00:00')",
                (cid, channel, "peer" if channel else None),
            )
            conn.execute(
                "INSERT INTO chat_messages (id, conversation_id, seq, role, content, status,"
                " created_at) VALUES (?, ?, 0, 'user', '[]', 'complete', '2026-10-05 00:00:00')",
                (f"m-{cid}", cid),
            )
            conn.execute(
                "INSERT INTO chat_reply_files (message_id, path, seq, added, removed)"
                " VALUES (?, 'a.py', 0, 1, 0)",
                (f"m-{cid}",),
            )

    command.upgrade(cfg, "head")

    with sqlite3.connect(db_path) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert not {"chat_messages", "chat_reply_files"} & tables
        columns = [r[1] for r in conn.execute("PRAGMA table_info(conversations)")]
        assert "archived_at" not in columns
        indexes = {r[1] for r in conn.execute("PRAGMA index_list(conversations)")}
        assert "idx_conversations_archived" not in indexes
        # Only the conversation a channel owns is kept; the web's own is gone.
        assert [r[0] for r in conn.execute("SELECT id FROM conversations")] == ["chan"]

    # The downgrade recreates the empty tables and the column; nothing is restored.
    command.downgrade(cfg, "0148")
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM chat_reply_files").fetchone()[0] == 0
        columns = [r[1] for r in conn.execute("PRAGMA table_info(conversations)")]
        assert "archived_at" in columns
        assert [r[0] for r in conn.execute("SELECT id FROM conversations")] == ["chan"]
