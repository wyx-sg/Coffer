"""Per-group inbound gating is configurable ("Configure when the bot answers in a group").

``require_mention`` (default on) keeps the bot silent in a group until it is
@mentioned/replied-to; turning it off admits an un-addressed (but still
owner-gated) group message. A message that @mentions the bot is answered even
when it also @mentions someone else.
"""

from __future__ import annotations

import pytest

from .conftest import ChannelEnv, inbound, wait_until


@pytest.mark.acceptance(
    spec="channels", scenario="require_mention on drops an un-addressed group message"
)
async def test_require_mention_on_drops_unaddressed_group_message(env: ChannelEnv) -> None:
    """With ``require_mention`` on (the default), an un-addressed group message —
    even from the owner — is dropped at the mention gate: no reply, no turn."""
    resource = await env.register_channel("tg")
    adapter = env.bind(resource)  # require_mention defaults to True
    await env.pair(resource, "owner", sender_id="owner-1")

    await env.processor.on_message(
        inbound(
            "tg",
            "grp-1",
            "just chatting amongst ourselves",
            chat_kind="group",
            addressed=False,
            sender_id="owner-1",
        )
    )

    assert adapter.sent == []
    assert await env.conversations() == []
    assert await env.peers.get_by_chat(resource.uid, "grp-1") is None


@pytest.mark.acceptance(
    spec="channels", scenario="require_mention off admits an un-addressed owner group message"
)
async def test_require_mention_off_admits_unaddressed_owner_message(env: ChannelEnv) -> None:
    """With ``require_mention`` off, an un-addressed group message from the owner
    passes the mention gate and drives a turn (still owner-gated: a non-owner
    would be refused by the sender_id checks below the gate)."""
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, require_mention=False)
    await env.pair(resource, "owner", sender_id="owner-1")

    await env.processor.on_message(
        inbound(
            "tg",
            "grp-1",
            "status update, no mention needed",
            chat_kind="group",
            addressed=False,
            sender_id="owner-1",
        )
    )
    await wait_until(lambda: "Hello world" in adapter.texts())

    assert await env.peers.get_by_chat(resource.uid, "grp-1") is not None


@pytest.mark.acceptance(
    spec="channels", scenario="a non-owner's un-addressed group message is dropped silently"
)
async def test_require_mention_off_drops_a_non_owners_chatter_silently(env: ChannelEnv) -> None:
    """With ``require_mention`` off a stranger's un-addressed message reaches the
    owner gate; it is dropped without a word, and only an ADDRESSED one is
    refused aloud — the bot is not the group's noisiest member."""
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, require_mention=False)
    await env.pair(resource, "owner", sender_id="owner-1")

    await env.processor.on_message(
        inbound("tg", "grp-1", "just chatting", chat_kind="group", addressed=False, sender_id="x-2")
    )
    assert adapter.sent == []
    assert await env.peers.get_by_chat(resource.uid, "grp-1") is None

    await env.processor.on_message(
        inbound("tg", "grp-1", "@bot do it", chat_kind="group", addressed=True, sender_id="x-2")
    )
    assert "owners can use it here" in adapter.sent[-1][1]


@pytest.mark.acceptance(
    spec="channels",
    scenario="a message that @mentions the bot alongside a human is answered",
)
async def test_a_mention_alongside_a_human_is_answered(
    env: ChannelEnv,
) -> None:
    """A group message that @mentions the bot drives a turn even when it also
    @mentions a human."""
    resource = await env.register_channel("tg")
    adapter = env.bind(resource)
    await env.pair(resource, "owner", sender_id="owner-1")

    await env.processor.on_message(
        inbound(
            "tg",
            "grp-1",
            "@bot @alice what's the plan",
            chat_kind="group",
            addressed=True,
            sender_id="owner-1",
            thread_id="th-1",
        )
    )
    await wait_until(lambda: "Hello world" in adapter.texts())

    assert await env.peers.get_by_chat(resource.uid, "grp-1") is not None
