"""ChannelPeerRepo CRUD over real SQLite + the channel_peers migration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from coffer.application.channel.store_ports import ChannelPeer

from .conftest import ChannelEnv

# ---------------------------------------------------------------------------
# Repo CRUD (schema from Base.metadata, FK pragma on)
# ---------------------------------------------------------------------------


def _peer(resource_uid: str, chat_id: str = "chat-1") -> ChannelPeer:
    return ChannelPeer(
        resource_uid=resource_uid,
        chat_id=chat_id,
        display_name="Owner",
        paired_at=datetime.now(tz=UTC),
    )


async def test_upsert_then_get_roundtrips_the_peer(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    await env.peers.upsert(_peer(resource.uid))

    peer = await env.peers.get_by_chat(resource.uid, "chat-1")
    assert peer is not None
    assert peer.resource_uid == resource.uid
    assert peer.chat_id == "chat-1"
    assert peer.display_name == "Owner"
    assert peer.paired_at.tzinfo is not None  # UTC re-attached on read-back


async def test_upsert_same_chat_replaces_in_place(env: ChannelEnv) -> None:
    """Re-pairing the SAME chat (e.g. a fresh pairing code from the same DM)
    updates the row rather than duplicating it. Multiple peers per channel
    are legal (see the multi-peer tests below), but a given ``(resource_uid,
    chat_id)`` pair remains exactly one row."""
    resource = await env.register_channel("tg")
    await env.peers.upsert(_peer(resource.uid, chat_id="chat-1"))
    updated = _peer(resource.uid, chat_id="chat-1")
    updated = ChannelPeer(
        resource_uid=updated.resource_uid,
        chat_id=updated.chat_id,
        display_name="New Name",
        paired_at=updated.paired_at,
    )
    await env.peers.upsert(updated)

    rows = await env.peers.list_by_resource(resource.uid)
    assert len(rows) == 1  # not duplicated
    peer = await env.peers.get_by_chat(resource.uid, "chat-1")
    assert peer is not None
    assert peer.chat_id == "chat-1"
    assert peer.display_name == "New Name"


async def test_owner_peer_unknown_resource_returns_none(env: ChannelEnv) -> None:
    assert await env.peers.owner_peer(99999) is None


async def test_owner_peer_is_the_earliest_pairing_not_whatever_sqlite_returns(
    env: ChannelEnv,
) -> None:
    """The bug this pins: ``notify`` addressed "the channel's peer" through a
    query with no ``ORDER BY``, so a private notification could land in a group
    chat. The owner chat is the earliest pairing — a group can only be added to
    a channel whose DM already works."""
    resource = await env.register_channel("tg")
    now = datetime.now(tz=UTC)
    group = ChannelPeer(
        resource_uid=resource.uid,
        chat_id="group-1",
        display_name="Group",
        paired_at=now,
    )
    dm = ChannelPeer(
        resource_uid=resource.uid,
        chat_id="dm-1",
        display_name="Owner",
        paired_at=now - timedelta(days=3),
    )
    # Inserted group-first so row order disagrees with pairing order.
    await env.peers.upsert(group)
    await env.peers.upsert(dm)

    owner = await env.peers.owner_peer(resource.uid)
    assert owner is not None
    assert owner.chat_id == "dm-1"


async def test_owner_peer_breaks_a_paired_at_tie_on_chat_id(env: ChannelEnv) -> None:
    """Two chats paired in the same instant still resolve to one answer, the
    same one on every call and on every machine that converged both."""
    resource = await env.register_channel("tg")
    now = datetime.now(tz=UTC)
    for chat_id in ("b-chat", "a-chat"):
        await env.peers.upsert(
            ChannelPeer(
                resource_uid=resource.uid,
                chat_id=chat_id,
                display_name=chat_id,
                paired_at=now,
            )
        )

    owner = await env.peers.owner_peer(resource.uid)
    assert owner is not None and owner.chat_id == "a-chat"


async def test_sender_id_roundtrips(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    await env.peers.upsert(
        ChannelPeer(
            resource_uid=resource.uid,
            chat_id="chat-1",
            display_name="Owner",
            paired_at=datetime.now(tz=UTC),
            sender_id="u-42",
        )
    )
    peer = await env.peers.get_by_chat(resource.uid, "chat-1")
    assert peer is not None
    assert peer.sender_id == "u-42"


# ---------------------------------------------------------------------------
# Multi-peer-per-channel (group/thread support, Task 3 — no migration)
# ---------------------------------------------------------------------------


async def test_multiple_peers_per_channel_addressable_by_chat(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    dm = _peer(resource.uid, chat_id="dm-1")
    group = _peer(resource.uid, chat_id="group-1")
    await env.peers.upsert(dm)
    await env.peers.upsert(group)

    got_dm = await env.peers.get_by_chat(resource.uid, "dm-1")
    got_group = await env.peers.get_by_chat(resource.uid, "group-1")
    assert got_dm is not None and got_dm.chat_id == "dm-1"
    assert got_group is not None and got_group.chat_id == "group-1"

    rows = await env.peers.list_by_resource(resource.uid)
    assert {row.chat_id for row in rows} == {"dm-1", "group-1"}


async def test_get_by_chat_unknown_chat_returns_none(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    await env.peers.upsert(_peer(resource.uid, chat_id="dm-1"))

    assert await env.peers.get_by_chat(resource.uid, "unknown-chat") is None


async def test_upsert_updates_only_the_matching_chat_row(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    await env.peers.upsert(_peer(resource.uid, chat_id="dm-1"))
    await env.peers.upsert(_peer(resource.uid, chat_id="group-1"))

    # Re-upsert the DM peer (e.g. re-pair) — the group row must survive.
    await env.peers.upsert(_peer(resource.uid, chat_id="dm-1"))

    rows = await env.peers.list_by_resource(resource.uid)
    assert {row.chat_id for row in rows} == {"dm-1", "group-1"}


async def test_sender_ids_lists_every_paired_sender(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    await env.peers.upsert(
        ChannelPeer(
            resource_uid=resource.uid,
            chat_id="dm-1",
            display_name="Owner",
            paired_at=datetime.now(tz=UTC),
            sender_id="u-owner",
        )
    )

    await env.peers.upsert(
        ChannelPeer(
            resource_uid=resource.uid,
            chat_id="dm-2",
            display_name="Guest",
            paired_at=datetime.now(tz=UTC),
            sender_id="u-guest",
        )
    )

    assert await env.peers.sender_ids(resource.uid) == {"u-owner", "u-guest"}


async def test_sender_ids_empty_when_no_sender_paired(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    await env.peers.upsert(_peer(resource.uid))  # no sender_id supplied

    assert await env.peers.sender_ids(resource.uid) == frozenset()


async def test_sender_ids_empty_for_unknown_resource(env: ChannelEnv) -> None:
    assert await env.peers.sender_ids(99999) == frozenset()


async def test_delete_by_sender_drops_the_person_everywhere_and_only_them(
    env: ChannelEnv,
) -> None:
    """Un-pairing a person takes their DM and every group they brought the bot
    into, in one write, and leaves the other people's rows alone."""
    resource = await env.register_channel("tg")
    now = datetime.now(tz=UTC)
    for chat, who in (("dm-a", "a"), ("grp", "a"), ("dm-b", "b")):
        await env.peers.upsert(ChannelPeer(resource.uid, chat, who.upper(), now, sender_id=who))

    assert sorted(await env.peers.delete_by_sender(resource.uid, "a")) == ["dm-a", "grp"]
    assert [p.chat_id for p in await env.peers.list_by_resource(resource.uid)] == ["dm-b"]
    assert await env.peers.delete_by_sender(resource.uid, "a") == []  # already gone


# ---------------------------------------------------------------------------
# ChannelThreadConversationRepo (per-thread conversation identity, "Key
# conversation identity by channel, chat and thread")
# ---------------------------------------------------------------------------


async def test_thread_repo_unknown_returns_none(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    assert await env.threads.get(resource.uid, "grp-1", "th-1") is None


async def test_thread_repo_set_active_conversation_upserts(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    await env.threads.set_active_conversation(resource.uid, "grp-1", "th-1", "conv-1")
    row = await env.threads.get(resource.uid, "grp-1", "th-1")
    assert row is not None
    assert row.active_conversation_id == "conv-1"
    assert row.preferred_agent is None
    assert row.thread_id == "th-1"

    # A second set updates the same row in place (not a duplicate).
    await env.threads.set_active_conversation(resource.uid, "grp-1", "th-1", "conv-2")
    row = await env.threads.get(resource.uid, "grp-1", "th-1")
    assert row is not None
    assert row.active_conversation_id == "conv-2"


async def test_thread_repo_set_preferred_agent_preserves_conversation(env: ChannelEnv) -> None:
    """Setting the sticky agent must not clobber the thread's active
    conversation, and vice versa — each upsert touches one field."""
    resource = await env.register_channel("tg")
    await env.threads.set_active_conversation(resource.uid, "grp-1", "th-1", "conv-1")
    await env.threads.set_preferred_agent(resource.uid, "grp-1", "th-1", "codex")

    row = await env.threads.get(resource.uid, "grp-1", "th-1")
    assert row is not None
    assert row.active_conversation_id == "conv-1"  # untouched by the agent set
    assert row.preferred_agent == "codex"


async def test_thread_repo_threads_are_independent(env: ChannelEnv) -> None:
    """Same group (chat_id), two threads → two independent rows."""
    resource = await env.register_channel("tg")
    await env.threads.set_active_conversation(resource.uid, "grp-1", "th-A", "conv-a")
    await env.threads.set_active_conversation(resource.uid, "grp-1", "th-B", "conv-b")

    row_a = await env.threads.get(resource.uid, "grp-1", "th-A")
    row_b = await env.threads.get(resource.uid, "grp-1", "th-B")
    assert row_a is not None and row_a.active_conversation_id == "conv-a"
    assert row_b is not None and row_b.active_conversation_id == "conv-b"


async def test_thread_repo_dm_is_the_empty_thread(env: ChannelEnv) -> None:
    """The DM (or a group's main chat) is ``thread_id=""`` — distinct from a
    thread of the same chat."""
    resource = await env.register_channel("tg")
    await env.threads.set_active_conversation(resource.uid, "owner", "", "conv-dm")
    await env.threads.set_active_conversation(resource.uid, "owner", "th-1", "conv-th")

    dm = await env.threads.get(resource.uid, "owner", "")
    thread = await env.threads.get(resource.uid, "owner", "th-1")
    assert dm is not None and dm.active_conversation_id == "conv-dm"
    assert thread is not None and thread.active_conversation_id == "conv-th"
