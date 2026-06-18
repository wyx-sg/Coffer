"""Sender-identity owner gate + first-class channel-driven audit (FR-014)."""

from __future__ import annotations

import pytest

from coffer.domain.audit import AuditEventType

from .conftest import ChannelEnv, inbound, wait_until

# -- sender-identity gate ------------------------------------------------------


@pytest.mark.acceptance(
    spec="009-channels", scenario="a group member who is not the paired sender is ignored"
)
async def test_message_from_a_different_sender_is_ignored(env: ChannelEnv) -> None:
    _resource, adapter = await env.paired_channel(sender_id="u-owner")

    # Same chat id (e.g. a group), but a different member sends it.
    await env.processor.on_message(inbound("tg", "owner", "do something", sender_id="u-intruder"))

    assert adapter.texts() == []  # no reply
    assert await env.chat.list_conversations() == []  # no turn started


async def test_matching_sender_passes_the_gate(env: ChannelEnv) -> None:
    _resource, adapter = await env.paired_channel(sender_id="u-owner")

    await env.processor.on_message(inbound("tg", "owner", "hi", sender_id="u-owner"))
    await wait_until(lambda: "Hello world" in adapter.texts())


async def test_message_with_no_sender_id_falls_back_to_chat_id(env: ChannelEnv) -> None:
    # Owner paired with a real sender id, but a later message arrives with none
    # (a transport could not supply one) — the owner must not be locked out.
    _resource, adapter = await env.paired_channel(sender_id="u-owner")

    await env.processor.on_message(inbound("tg", "owner", "hi", sender_id=""))
    await wait_until(lambda: "Hello world" in adapter.texts())


async def test_legacy_peer_without_sender_id_accepts_on_chat_id(env: ChannelEnv) -> None:
    # Paired before the gate gained sender awareness (sender_id is None).
    _resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "hi", sender_id="whatever"))
    await wait_until(lambda: "Hello world" in adapter.texts())


# -- first-class channel-driven audit ------------------------------------------


@pytest.mark.acceptance(
    spec="009-channels", scenario="a channel-driven turn is audited with channel, peer, and agent"
)
async def test_channel_turn_started_is_audited(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "hi"))
    await wait_until(lambda: "Hello world" in adapter.texts())

    entries = await env.audit_entries(AuditEventType.CHANNEL_TURN_STARTED.value)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.details["channel"] == "tg"
    assert entry.details["chat_id"] == "owner"
    assert entry.details["agent_key"] == "builtin"
    peer = await env.peers.get(resource.id)
    assert peer is not None
    assert entry.details["conversation_id"] == peer.active_conversation_id
