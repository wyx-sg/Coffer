"""Inbound pairing: claiming a code binds the owner; everyone else is ignored.

Drives the real InboundProcessor + PairingManager + ChannelPeerRepo (real
SQLite) through the FakeChannelAdapter seam.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from coffer.domain.resource import Resource

from .conftest import ChannelEnv, FakeChannelAdapter, inbound, wait_until


@pytest.mark.acceptance(spec="channels", scenario="pair by sending the code")
async def test_sending_the_code_pairs_the_chat_and_consumes_the_code(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    adapter = env.bind(resource)
    code, _expires = env.pairing.issue("tg")

    await env.processor.on_message(inbound("tg", "chat-1", code, sender_display="Alice"))

    peer = await env.peers.owner_peer(resource.id)
    assert peer is not None
    assert peer.chat_id == "chat-1"
    assert peer.display_name == "Alice"

    assert len(adapter.sent) == 1
    chat_id, text = adapter.sent[0]
    assert chat_id == "chat-1"
    assert text.startswith("✅ Paired.")
    assert "/help" in text  # the confirmation carries the command list

    entries = await env.audit_entries("channel_paired", resource)
    assert len(entries) == 1
    assert entries[0].details == {"chat_id": "chat-1", "display_name": "Alice"}

    # The code was consumed: the same code from another chat does not re-pair.
    await env.processor.on_message(inbound("tg", "chat-2", code))
    peer = await env.peers.owner_peer(resource.id)
    assert peer is not None
    assert peer.chat_id == "chat-1"
    assert len(adapter.sent) == 1  # no confirmation for the second chat
    assert len(await env.audit_entries("channel_paired", resource)) == 1


@pytest.mark.acceptance(spec="channels", scenario="ignore messages from strangers")
async def test_message_from_a_different_chat_is_silently_ignored(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel("tg", chat_id="owner")

    await env.processor.on_message(inbound("tg", "stranger", "hello bot"))

    assert adapter.sent == []
    assert await env.chat.list_conversations() == []
    peer = await env.peers.owner_peer(resource.id)
    assert peer is not None
    assert peer.chat_id == "owner"


@pytest.mark.acceptance(spec="channels", scenario="an expired or wrong code does not pair")
async def test_wrong_guesses_get_no_reply_and_exhaust_the_code(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    adapter = env.bind(resource)
    code, _expires = env.pairing.issue("tg")

    # Burn every attempt with wrong guesses: no reply, no peer row.
    for _ in range(10):
        await env.processor.on_message(inbound("tg", "chat-1", "WRONGGUESS"))
    assert adapter.sent == []
    assert await env.peers.owner_peer(resource.id) is None

    # Attempt exhaustion invalidated the code — even the right one fails now.
    await env.processor.on_message(inbound("tg", "chat-1", code))
    assert await env.peers.owner_peer(resource.id) is None
    assert adapter.sent == []
    assert env.pairing.pending("tg") is False


async def _pair_owner_with_a_group(env: ChannelEnv) -> tuple[Resource, FakeChannelAdapter]:
    """A channel paired from ``old-dm`` (sender ``old-1``) that has also answered
    ``old-1`` in group ``grp-1`` — so a group peer row inherits the old owner."""
    resource = await env.register_channel("tg")
    adapter = env.bind(resource)
    # Report ``adapter`` as the live one, which is what ``notify`` reads.
    env.runtime._running[resource.name] = SimpleNamespace(adapter=adapter)
    code, _ = env.pairing.issue("tg")
    await env.processor.on_message(inbound("tg", "old-dm", code, sender_id="old-1"))
    await env.processor.on_message(
        inbound(
            "tg",
            "grp-1",
            "@bot hi",
            chat_kind="group",
            addressed=True,
            sender_id="old-1",
            thread_id="th-1",
        )
    )
    await wait_until(lambda: "Hello world" in adapter.texts())
    assert await env.peers.get_by_chat(resource.id, "grp-1") is not None
    return resource, adapter


@pytest.mark.acceptance(spec="channels", scenario="pairing from another account replaces the owner")
async def test_pairing_from_another_account_replaces_the_owner(env: ChannelEnv) -> None:
    """spec channels "Pair exactly one owner with a single-use code": the code
    "binds its sender as the channel's sole peer, replacing any previous peer".
    Every trace of the previous owner's authority goes; the new owner gets all of
    it — DM gate, notify default target, group owner gate."""
    resource, adapter = await _pair_owner_with_a_group(env)
    code, _ = env.pairing.issue("tg")
    await env.processor.on_message(inbound("tg", "new-dm", code, sender_id="new-1"))

    peers = await env.peers.list_by_resource(resource.id)
    assert [(p.chat_id, p.sender_id) for p in peers] == [("new-dm", "new-1")]
    assert await env.peers.owner_sender_id(resource.id) == "new-1"

    # (1) The old owner's DM no longer passes the owner gate: no reply, no turn.
    conversations_before = len(await env.chat.list_conversations())
    sent_before = len(adapter.sent)
    await env.processor.on_message(inbound("tg", "old-dm", "still mine?", sender_id="old-1"))
    assert len(adapter.sent) == sent_before
    assert len(await env.chat.list_conversations()) == conversations_before

    # (2) The new owner's DM drives a turn.
    await env.processor.on_message(inbound("tg", "new-dm", "hello", sender_id="new-1"))
    await wait_until(lambda: any(c == "new-dm" and t == "Hello world" for c, t in adapter.sent))

    # (3) notify without a chat goes to the new owner.
    await env.service.notify(resource.uid, "build finished", actor="test")
    assert adapter.sent[-1] == ("new-dm", "build finished")

    # (4) The group gate follows the new owner: the old one is refused, the new
    # one accepted and recorded as the group's peer.
    await env.processor.on_message(
        inbound("tg", "grp-1", "@bot again", chat_kind="group", sender_id="old-1", thread_id="t2")
    )
    assert "Not authorized" in adapter.sent[-1][1]
    await env.processor.on_message(
        inbound(
            "tg", "grp-1", "@bot mine now", chat_kind="group", sender_id="new-1", thread_id="t3"
        )
    )
    await wait_until(
        lambda: any(
            r[0] == "grp-1" and r[2] == "t3" and r[1] == "Hello world" for r in adapter.sent_routed
        )
    )
    group = await env.peers.get_by_chat(resource.id, "grp-1")
    assert group is not None
    assert group.sender_id == "new-1"


async def test_re_pairing_from_the_same_account_keeps_its_groups(env: ChannelEnv) -> None:
    """Re-pairing by the same owner (same sender, from a chat not yet paired) is
    not an ownership change: the new chat pairs and nothing the owner already
    had — DM, groups, group gate — is dropped."""
    resource, adapter = await _pair_owner_with_a_group(env)
    code, _ = env.pairing.issue("tg")
    await env.processor.on_message(inbound("tg", "old-dm-2", code, sender_id="old-1"))

    assert adapter.sent[-1][0] == "old-dm-2"
    assert adapter.sent[-1][1].startswith("✅ Paired.")
    peers = await env.peers.list_by_resource(resource.id)
    assert sorted((p.chat_id, p.sender_id) for p in peers) == [
        ("grp-1", "old-1"),
        ("old-dm", "old-1"),
        ("old-dm-2", "old-1"),
    ]
    assert await env.peers.owner_sender_id(resource.id) == "old-1"
    assert len(await env.audit_entries("channel_paired", resource)) == 2
