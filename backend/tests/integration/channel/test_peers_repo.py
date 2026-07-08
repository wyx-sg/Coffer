"""ChannelPeerRepo CRUD over real SQLite + the channel_peers migration."""

from __future__ import annotations

import pathlib
import sqlite3
from datetime import UTC, datetime

from alembic import command
from alembic.config import Config as AlembicConfig

from coffer.application.channel.ports import ChannelPeer

from .conftest import ChannelEnv

# ---------------------------------------------------------------------------
# Repo CRUD (schema from Base.metadata, FK pragma on)
# ---------------------------------------------------------------------------


def _peer(resource_id: int, chat_id: str = "chat-1") -> ChannelPeer:
    return ChannelPeer(
        resource_id=resource_id,
        chat_id=chat_id,
        display_name="Owner",
        paired_at=datetime.now(tz=UTC),
        active_conversation_id=None,
    )


async def test_upsert_then_get_roundtrips_the_peer(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    await env.peers.upsert(_peer(resource.id))

    peer = await env.peers.get(resource.id)
    assert peer is not None
    assert peer.resource_id == resource.id
    assert peer.chat_id == "chat-1"
    assert peer.display_name == "Owner"
    assert peer.paired_at.tzinfo is not None  # UTC re-attached on read-back
    assert peer.active_conversation_id is None


async def test_upsert_same_chat_replaces_in_place(env: ChannelEnv) -> None:
    """Re-pairing the SAME chat (e.g. a fresh pairing code from the same DM)
    updates the row rather than duplicating it. Multiple peers per channel
    are legal (see the multi-peer tests below), but a given ``(resource_id,
    chat_id)`` pair remains exactly one row."""
    resource = await env.register_channel("tg")
    await env.peers.upsert(_peer(resource.id, chat_id="chat-1"))
    updated = _peer(resource.id, chat_id="chat-1")
    updated = ChannelPeer(
        resource_id=updated.resource_id,
        chat_id=updated.chat_id,
        display_name="New Name",
        paired_at=updated.paired_at,
        active_conversation_id=updated.active_conversation_id,
    )
    await env.peers.upsert(updated)

    rows = await env.peers.list_by_resource(resource.id)
    assert len(rows) == 1  # not duplicated
    peer = await env.peers.get(resource.id)
    assert peer is not None
    assert peer.chat_id == "chat-1"
    assert peer.display_name == "New Name"


async def test_set_active_conversation_updates_and_clears(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    await env.peers.upsert(_peer(resource.id))

    await env.peers.set_active_conversation(resource.id, "chat-1", "conv-9")
    peer = await env.peers.get(resource.id)
    assert peer is not None
    assert peer.active_conversation_id == "conv-9"

    await env.peers.set_active_conversation(resource.id, "chat-1", None)
    peer = await env.peers.get(resource.id)
    assert peer is not None
    assert peer.active_conversation_id is None


async def test_get_unknown_resource_returns_none(env: ChannelEnv) -> None:
    assert await env.peers.get(99999) is None


async def test_sender_id_and_preferences_roundtrip(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    await env.peers.upsert(
        ChannelPeer(
            resource_id=resource.id,
            chat_id="chat-1",
            display_name="Owner",
            paired_at=datetime.now(tz=UTC),
            active_conversation_id=None,
            sender_id="u-42",
            preferred_agent="codex",
        )
    )
    peer = await env.peers.get(resource.id)
    assert peer is not None
    assert peer.sender_id == "u-42"
    assert peer.preferred_agent == "codex"


async def test_legacy_peer_reads_new_fields_as_none(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    await env.peers.upsert(_peer(resource.id))  # no new fields supplied
    peer = await env.peers.get(resource.id)
    assert peer is not None
    assert peer.sender_id is None
    assert peer.preferred_agent is None


async def test_set_preferences_updates_and_preserves_active_conversation(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    await env.peers.upsert(_peer(resource.id))
    await env.peers.set_active_conversation(resource.id, "chat-1", "conv-7")

    await env.peers.set_preferences(resource.id, preferred_agent="claude_code")
    peer = await env.peers.get(resource.id)
    assert peer is not None
    assert peer.preferred_agent == "claude_code"
    assert peer.active_conversation_id == "conv-7"  # preferences don't disturb it


# ---------------------------------------------------------------------------
# Multi-peer-per-channel (group/thread support, Task 3 — no migration)
# ---------------------------------------------------------------------------


async def test_multiple_peers_per_channel_addressable_by_chat(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    dm = _peer(resource.id, chat_id="dm-1")
    group = _peer(resource.id, chat_id="group-1")
    await env.peers.upsert(dm)
    await env.peers.upsert(group)

    got_dm = await env.peers.get_by_chat(resource.id, "dm-1")
    got_group = await env.peers.get_by_chat(resource.id, "group-1")
    assert got_dm is not None and got_dm.chat_id == "dm-1"
    assert got_group is not None and got_group.chat_id == "group-1"

    rows = await env.peers.list_by_resource(resource.id)
    assert {row.chat_id for row in rows} == {"dm-1", "group-1"}


async def test_get_by_chat_unknown_chat_returns_none(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    await env.peers.upsert(_peer(resource.id, chat_id="dm-1"))

    assert await env.peers.get_by_chat(resource.id, "unknown-chat") is None


async def test_upsert_updates_only_the_matching_chat_row(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    await env.peers.upsert(_peer(resource.id, chat_id="dm-1"))
    await env.peers.upsert(_peer(resource.id, chat_id="group-1"))

    # Re-upsert the DM peer (e.g. re-pair) — the group row must survive.
    await env.peers.upsert(_peer(resource.id, chat_id="dm-1"))

    rows = await env.peers.list_by_resource(resource.id)
    assert {row.chat_id for row in rows} == {"dm-1", "group-1"}


async def test_owner_sender_id_returns_first_paired_sender(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    await env.peers.upsert(
        ChannelPeer(
            resource_id=resource.id,
            chat_id="dm-1",
            display_name="Owner",
            paired_at=datetime.now(tz=UTC),
            active_conversation_id=None,
            sender_id="u-owner",
        )
    )

    assert await env.peers.owner_sender_id(resource.id) == "u-owner"


async def test_owner_sender_id_none_when_no_sender_paired(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    await env.peers.upsert(_peer(resource.id))  # no sender_id supplied

    assert await env.peers.owner_sender_id(resource.id) is None


async def test_owner_sender_id_none_for_unknown_resource(env: ChannelEnv) -> None:
    assert await env.peers.owner_sender_id(99999) is None


# ---------------------------------------------------------------------------
# ChannelThreadConversationRepo (per-thread conversation identity, FR-032)
# ---------------------------------------------------------------------------


async def test_thread_repo_unknown_returns_none(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    assert await env.threads.get(resource.id, "grp-1", "th-1") is None


async def test_thread_repo_set_active_conversation_upserts(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    await env.threads.set_active_conversation(resource.id, "grp-1", "th-1", "conv-1")
    row = await env.threads.get(resource.id, "grp-1", "th-1")
    assert row is not None
    assert row.active_conversation_id == "conv-1"
    assert row.preferred_agent is None
    assert row.thread_id == "th-1"

    # A second set updates the same row in place (not a duplicate).
    await env.threads.set_active_conversation(resource.id, "grp-1", "th-1", "conv-2")
    row = await env.threads.get(resource.id, "grp-1", "th-1")
    assert row is not None
    assert row.active_conversation_id == "conv-2"


async def test_thread_repo_set_preferred_agent_preserves_conversation(env: ChannelEnv) -> None:
    """Setting the sticky agent must not clobber the thread's active
    conversation, and vice versa — each upsert touches one field."""
    resource = await env.register_channel("tg")
    await env.threads.set_active_conversation(resource.id, "grp-1", "th-1", "conv-1")
    await env.threads.set_preferred_agent(resource.id, "grp-1", "th-1", "codex")

    row = await env.threads.get(resource.id, "grp-1", "th-1")
    assert row is not None
    assert row.active_conversation_id == "conv-1"  # untouched by the agent set
    assert row.preferred_agent == "codex"


async def test_thread_repo_threads_are_independent(env: ChannelEnv) -> None:
    """Same group (chat_id), two threads → two independent rows."""
    resource = await env.register_channel("tg")
    await env.threads.set_active_conversation(resource.id, "grp-1", "th-A", "conv-a")
    await env.threads.set_active_conversation(resource.id, "grp-1", "th-B", "conv-b")

    row_a = await env.threads.get(resource.id, "grp-1", "th-A")
    row_b = await env.threads.get(resource.id, "grp-1", "th-B")
    assert row_a is not None and row_a.active_conversation_id == "conv-a"
    assert row_b is not None and row_b.active_conversation_id == "conv-b"


async def test_thread_repo_dm_is_the_empty_thread(env: ChannelEnv) -> None:
    """The DM (or a group's main chat) is ``thread_id=""`` — distinct from a
    thread of the same chat."""
    resource = await env.register_channel("tg")
    await env.threads.set_active_conversation(resource.id, "owner", "", "conv-dm")
    await env.threads.set_active_conversation(resource.id, "owner", "th-1", "conv-th")

    dm = await env.threads.get(resource.id, "owner", "")
    thread = await env.threads.get(resource.id, "owner", "th-1")
    assert dm is not None and dm.active_conversation_id == "conv-dm"
    assert thread is not None and thread.active_conversation_id == "conv-th"


# ---------------------------------------------------------------------------
# Migration 20260612_0015 (same alembic harness as the persistence tests)
# ---------------------------------------------------------------------------

_ALEMBIC_INI = (
    pathlib.Path(__file__).resolve().parents[3]
    / "coffer"
    / "infrastructure"
    / "persistence"
    / "migrations"
    / "alembic.ini"
)


def test_migration_0015_creates_channel_peers(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    db_path = tmp_path / "migrate.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    assert _ALEMBIC_INI.is_file(), f"alembic.ini not found at {_ALEMBIC_INI}"
    cfg = AlembicConfig(str(_ALEMBIC_INI))

    command.upgrade(cfg, "head")

    conn = sqlite3.connect(str(db_path))
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(channel_peers)")}
        assert columns == {
            "id",
            "resource_id",
            "chat_id",
            "display_name",
            "paired_at",
            "active_conversation_id",
            "sender_id",
            "preferred_agent",
        }
        fks = conn.execute("PRAGMA foreign_key_list(channel_peers)").fetchall()
        assert len(fks) == 1
        # (id, seq, table, from, to, on_update, on_delete, match)
        assert fks[0][2] == "resources"
        assert fks[0][3] == "resource_id"
        assert fks[0][6] == "CASCADE"
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(channel_peers)")}
        assert "idx_channel_peers_resource" in indexes
    finally:
        conn.close()

    # The downgrade tears the table back out (reversible chain).
    command.downgrade(cfg, "0014")
    conn = sqlite3.connect(str(db_path))
    try:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert "channel_peers" not in tables
    finally:
        conn.close()


def test_migration_0041_creates_thread_table_and_backfills_dm(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    """0041 (FR-032) creates ``channel_thread_conversations`` and backfills each
    existing peer as its ``thread_id=""`` row, carrying the peer's active
    conversation + sticky agent so no in-flight DM conversation is lost."""
    db_path = tmp_path / "migrate_threads.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = AlembicConfig(str(_ALEMBIC_INI))

    # Schema as of just before the new migration; seed a paired peer whose DM
    # already has an active conversation and a sticky agent.
    command.upgrade(cfg, "0040")
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO resources (kind, name, config_json, enabled, created_at, updated_at) "
            "VALUES ('channel', 'tg', '{}', 1, '2026-07-08', '2026-07-08')"
        )
        conn.execute(
            "INSERT INTO channel_peers "
            "(resource_id, chat_id, display_name, paired_at, active_conversation_id, "
            "sender_id, preferred_agent) "
            "VALUES (1, 'owner', 'Owner', '2026-07-08T00:00:00+00:00', 'conv-dm', 'u-1', 'codex')"
        )
        conn.commit()
    finally:
        conn.close()

    command.upgrade(cfg, "head")

    conn = sqlite3.connect(str(db_path))
    try:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(channel_thread_conversations)")
        }
        assert columns == {
            "id",
            "resource_id",
            "chat_id",
            "thread_id",
            "active_conversation_id",
            "preferred_agent",
            "updated_at",
        }
        rows = conn.execute(
            "SELECT resource_id, chat_id, thread_id, active_conversation_id, preferred_agent "
            "FROM channel_thread_conversations"
        ).fetchall()
        # The DM conversation is backfilled as the thread_id="" row.
        assert rows == [(1, "owner", "", "conv-dm", "codex")]
        indexes = {
            row[1] for row in conn.execute("PRAGMA index_list(channel_thread_conversations)")
        }
        assert "idx_channel_thread_conv_resource" in indexes
    finally:
        conn.close()

    # The downgrade drops the table (reversible chain).
    command.downgrade(cfg, "0040")
    conn = sqlite3.connect(str(db_path))
    try:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert "channel_thread_conversations" not in tables
    finally:
        conn.close()
