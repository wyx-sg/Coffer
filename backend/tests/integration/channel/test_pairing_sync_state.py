"""Channel pairings as a synced state area (spec vault-sync ``## What syncs``).

A channel travels now, so rebinding it to another machine is a thing that
happens — and a channel that arrived without its pairings would make the owner
re-pair from their phone every time, which is the cost the area exists to
avoid. What must travel is platform identity; what must NOT is the pointer at
this machine's own conversation, because conversations are machine-local and a
published pointer names a row the other machine does not have.

These tests drive the provider directly. The document is what crosses, so the
document is what is asserted: what it carries, what it must not carry, and what
importing one does to a store that already holds its own answer.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.application.channel.sync_state import AREA, ChannelPeerSyncState, doc_path

from .conftest import ChannelEnv


def _provider(env: ChannelEnv) -> ChannelPeerSyncState:
    return ChannelPeerSyncState(env.resources, env.peers)


async def test_the_exported_document_carries_platform_identity_only(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    peer = await env.pair(resource, chat_id="chat-42", sender_id="sender-7")
    await env.peers.set_active_conversation(resource.id, peer.chat_id, "conv-local-only")

    docs, _owned = await _provider(env).export_docs()

    assert [path for path, _ in docs] == [doc_path("tg", "chat-42")]
    payload = docs[0][1]
    assert payload["channel"] == "tg"
    assert payload["chat_id"] == "chat-42"
    assert payload["sender_id"] == "sender-7"
    # The pointer is not in the document, and not merely absent as a key: it
    # must not be reconstructible from anything the document does carry.
    assert "active_conversation_id" not in payload
    assert "conv-local-only" not in str(payload)
    assert AREA == "channel-peers"


@pytest.mark.acceptance(spec="vault-sync", scenario="a channel's pairings travel with it")
async def test_an_arriving_pairing_lands_without_disturbing_the_local_conversation(
    env: ChannelEnv,
) -> None:
    """The case a rebind actually produces.

    The other machine publishes the pairing it holds; this machine may already
    have a conversation open in that same chat. The pairing must land — that is
    the point — and the conversation pointer must be the one this machine set,
    because the arriving document has nothing true to say about it.
    """
    resource = await env.register_channel("tg")
    provider = _provider(env)

    arriving = [
        (
            doc_path("tg", "chat-42"),
            {
                "channel": "tg",
                "chat_id": "chat-42",
                "display_name": "Owner",
                "sender_id": "sender-7",
                "preferred_agent": "claude_code",
                "paired_at": datetime(2026, 9, 1, tzinfo=UTC).isoformat(),
            },
        )
    ]

    # Nothing here yet: the channel was just rebound to this machine.
    assert await env.peers.get_by_chat(resource.id, "chat-42") is None
    assert await provider.import_docs(arriving) == []

    landed = await env.peers.get_by_chat(resource.id, "chat-42")
    assert landed is not None
    assert landed.sender_id == "sender-7"
    assert landed.preferred_agent == "claude_code"
    assert landed.active_conversation_id is None

    # Now this machine opens a conversation in that chat, and the other machine
    # publishes the same pairing again on its next round.
    await env.peers.set_active_conversation(resource.id, "chat-42", "conv-mine")
    assert await provider.import_docs(arriving) == []

    kept = await env.peers.get_by_chat(resource.id, "chat-42")
    assert kept is not None
    assert kept.active_conversation_id == "conv-mine"


async def test_a_pairing_for_a_channel_not_here_yet_is_held_rather_than_dropped(
    env: ChannelEnv,
) -> None:
    """Resource documents and state documents are applied in no fixed order.

    A pairing whose channel has not landed yet is "not yet", not "never": it is
    reported, so the round holds the path and retries it — and, crucially, so
    the next export cannot publish it as a deletion the owner never made.
    """
    failures = await _provider(env).import_docs(
        [(doc_path("ghost", "chat-1"), {"channel": "ghost", "chat_id": "chat-1"})]
    )
    assert len(failures) == 1
    assert "not registered here yet" in failures[0][1]


async def test_a_malformed_pairing_is_reported_rather_than_silently_skipped(
    env: ChannelEnv,
) -> None:
    failures = await _provider(env).import_docs([(doc_path("tg", "chat-1"), {"channel": "tg"})])
    assert len(failures) == 1
    assert "chat_id" in failures[0][1]


async def test_an_unpairing_deletes_exactly_that_chat(env: ChannelEnv) -> None:
    """A deletion reaches here only because somebody actually un-paired.

    The document path is sanitised and therefore not reversible into a chat id,
    so the provider re-addresses its own peers to find the one that matches —
    and must leave the channel's other chats alone, since a channel holds one
    peer row per DM, group and thread.
    """
    resource = await env.register_channel("tg")
    await env.pair(resource, chat_id="chat-42")
    await env.pair(resource, chat_id="chat-99")

    await _provider(env).delete_docs([doc_path("tg", "chat-42")])

    assert await env.peers.get_by_chat(resource.id, "chat-42") is None
    assert await env.peers.get_by_chat(resource.id, "chat-99") is not None

    # A path naming a channel this machine does not hold is nothing to do here.
    await _provider(env).delete_docs([doc_path("ghost", "chat-1")])
