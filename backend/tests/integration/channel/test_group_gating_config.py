"""FR-035: per-group inbound gating is configurable.

``require_mention`` (default on) keeps the bot silent in a group until it is
@mentioned/replied-to; turning it off admits an un-addressed (but still
owner-gated) group message. ``ignore_other_mentions`` (opt-in) silently drops a
group message that @mentions any non-bot user, even when it also mentions the
bot, so a bot in a busy group never butts into human-aimed traffic.
"""

from __future__ import annotations

import pytest

from .conftest import ChannelEnv, inbound, wait_until


@pytest.mark.acceptance(
    spec="009-channels", scenario="require_mention on drops an un-addressed group message"
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
    assert await env.chat.list_conversations() == []
    assert await env.peers.get_by_chat(resource.id, "grp-1") is None


@pytest.mark.acceptance(
    spec="009-channels", scenario="require_mention off admits an un-addressed owner group message"
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

    assert await env.peers.get_by_chat(resource.id, "grp-1") is not None


@pytest.mark.acceptance(
    spec="009-channels",
    scenario="ignore_other_mentions drops a message that also @mentions a human",
)
async def test_ignore_other_mentions_drops_message_mentioning_a_human(env: ChannelEnv) -> None:
    """With ``ignore_other_mentions`` on, a group message that @mentions another
    user is dropped silently — no reply, no turn — even though it also mentions
    the bot and comes from the owner."""
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, ignore_other_mentions=True)
    await env.pair(resource, "owner", sender_id="owner-1")

    await env.processor.on_message(
        inbound(
            "tg",
            "grp-1",
            "@bot @alice can you two sort this out",
            chat_kind="group",
            addressed=True,
            mentions_others=True,
            sender_id="owner-1",
            thread_id="th-1",
        )
    )

    assert adapter.sent == []
    assert await env.chat.list_conversations() == []
    assert await env.peers.get_by_chat(resource.id, "grp-1") is None


@pytest.mark.acceptance(
    spec="009-channels",
    scenario="ignore_other_mentions off still answers when @mentioned alongside a human",
)
async def test_ignore_other_mentions_off_still_answers_when_mentioned_with_a_human(
    env: ChannelEnv,
) -> None:
    """With ``ignore_other_mentions`` off (the default), a group message that
    @mentions the bot still drives a turn even when it also @mentions a human."""
    resource = await env.register_channel("tg")
    adapter = env.bind(resource)  # ignore_other_mentions defaults to False
    await env.pair(resource, "owner", sender_id="owner-1")

    await env.processor.on_message(
        inbound(
            "tg",
            "grp-1",
            "@bot @alice what's the plan",
            chat_kind="group",
            addressed=True,
            mentions_others=True,
            sender_id="owner-1",
            thread_id="th-1",
        )
    )
    await wait_until(lambda: "Hello world" in adapter.texts())

    assert await env.peers.get_by_chat(resource.id, "grp-1") is not None
