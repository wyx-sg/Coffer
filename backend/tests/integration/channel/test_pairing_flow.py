"""Inbound pairing: claiming a code binds the owner; everyone else is ignored.

Drives the real InboundProcessor + PairingManager + ChannelPeerRepo (real
SQLite) through the FakeChannelAdapter seam.
"""

from __future__ import annotations

import pytest

from .conftest import ChannelEnv, inbound


@pytest.mark.acceptance(spec="009-channels", scenario="pair by sending the code")
async def test_sending_the_code_pairs_the_chat_and_consumes_the_code(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    adapter = env.bind(resource)
    code, _expires = env.pairing.issue("tg")

    await env.processor.on_message(inbound("tg", "chat-1", code, sender_display="Alice"))

    peer = await env.peers.get(resource.id)
    assert peer is not None
    assert peer.chat_id == "chat-1"
    assert peer.display_name == "Alice"
    assert peer.active_conversation_id is None

    assert len(adapter.sent) == 1
    chat_id, text = adapter.sent[0]
    assert chat_id == "chat-1"
    assert text.startswith("✅ Paired.")
    assert "/help" in text  # the confirmation carries the command list

    entries = await env.audit_entries("channel_paired", name="tg")
    assert len(entries) == 1
    assert entries[0].details == {"chat_id": "chat-1", "display_name": "Alice"}

    # The code was consumed: the same code from another chat does not re-pair.
    await env.processor.on_message(inbound("tg", "chat-2", code))
    peer = await env.peers.get(resource.id)
    assert peer is not None
    assert peer.chat_id == "chat-1"
    assert len(adapter.sent) == 1  # no confirmation for the second chat
    assert len(await env.audit_entries("channel_paired", name="tg")) == 1


@pytest.mark.acceptance(spec="009-channels", scenario="ignore messages from strangers")
async def test_message_from_a_different_chat_is_silently_ignored(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel("tg", chat_id="owner")

    await env.processor.on_message(inbound("tg", "stranger", "hello bot"))

    assert adapter.sent == []
    assert await env.chat.list_conversations() == []
    peer = await env.peers.get(resource.id)
    assert peer is not None
    assert peer.chat_id == "owner"


@pytest.mark.acceptance(spec="009-channels", scenario="an expired or wrong code does not pair")
async def test_wrong_guesses_get_no_reply_and_exhaust_the_code(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    adapter = env.bind(resource)
    code, _expires = env.pairing.issue("tg")

    # Burn every attempt with wrong guesses: no reply, no peer row.
    for _ in range(10):
        await env.processor.on_message(inbound("tg", "chat-1", "WRONGGUESS"))
    assert adapter.sent == []
    assert await env.peers.get(resource.id) is None

    # Attempt exhaustion invalidated the code — even the right one fails now.
    await env.processor.on_message(inbound("tg", "chat-1", code))
    assert await env.peers.get(resource.id) is None
    assert adapter.sent == []
    assert env.pairing.pending("tg") is False
