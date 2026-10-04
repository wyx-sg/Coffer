"""A message to a stale conversation opens a new one, and a message with no
sender is refused.

Spec channels "Open a new conversation after an idle period", "Open a new
conversation when the active one is archived" and "Refuse a message with an
empty sender id".
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from coffer.application.channel.store_ports import ChannelPeer

from .conftest import ChannelEnv, inbound, wait_until

NOTICE = "Started a new conversation after 24 h idle"


async def _age(env: ChannelEnv, conversation_id: str, hours: float) -> None:
    await env.chat._conversations.touch(
        conversation_id, datetime.now(tz=UTC) - timedelta(hours=hours)
    )


async def _say(env: ChannelEnv, adapter: object, text: str, **kw: object) -> None:
    before = len(adapter.texts())  # type: ignore[attr-defined]
    await env.processor.on_message(inbound("tg", "owner", text, **kw))  # type: ignore[arg-type]
    await wait_until(lambda: "Hello world" in adapter.texts()[before:])  # type: ignore[attr-defined]


@pytest.mark.acceptance(
    spec="channels", scenario="a chat idle past the configured hours opens a new conversation"
)
async def test_an_idle_chat_opens_a_new_conversation_and_says_so(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel()
    await _say(env, adapter, "first")
    first = await env.active_conversation(resource)
    assert first is not None
    await _age(env, first, 25)

    await _say(env, adapter, "second")

    second = await env.active_conversation(resource)
    assert second is not None and second != first
    assert any(NOTICE in text for text in adapter.texts())
    # The old conversation is still there, in the list.
    assert (await env.chat.get_conversation(first)).archived_at is None


@pytest.mark.acceptance(
    spec="channels", scenario="a chat active within the idle period keeps its conversation"
)
async def test_a_chat_active_within_the_window_keeps_its_conversation(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel()
    await _say(env, adapter, "first")
    first = await env.active_conversation(resource)
    assert first is not None
    await _age(env, first, 23)

    await _say(env, adapter, "second")

    assert await env.active_conversation(resource) == first
    assert not any(NOTICE in text for text in adapter.texts())


@pytest.mark.acceptance(spec="channels", scenario="zero idle hours never opens a new conversation")
async def test_zero_hours_never_rolls_a_conversation_over(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, new_conversation_after_idle_hours=0)
    await env.pair(resource)
    await _say(env, adapter, "first")
    first = await env.active_conversation(resource)
    assert first is not None
    await _age(env, first, 24 * 90)

    await _say(env, adapter, "second")

    assert await env.active_conversation(resource) == first


@pytest.mark.acceptance(
    spec="channels", scenario="the idle period applies to each group thread's conversation"
)
async def test_the_idle_period_applies_per_thread(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel()

    def msg(thread: str, text: str) -> object:
        return inbound(
            "tg",
            "grp-1",
            text,
            chat_kind="group",
            addressed=True,
            sender_id="owner",
            thread_id=thread,
        )

    for thread in ("t1", "t2"):
        await env.processor.on_message(msg(thread, "hi"))  # type: ignore[arg-type]
    await wait_until(lambda: adapter.texts().count("Hello world") >= 2)
    t1 = await env.active_conversation(resource, "grp-1", "t1")
    t2 = await env.active_conversation(resource, "grp-1", "t2")
    assert t1 and t2 and t1 != t2
    await _age(env, t1, 30)

    await env.processor.on_message(msg("t1", "again"))  # type: ignore[arg-type]
    await env.processor.on_message(msg("t2", "again"))  # type: ignore[arg-type]
    await wait_until(lambda: adapter.texts().count("Hello world") >= 4)

    assert await env.active_conversation(resource, "grp-1", "t1") != t1
    assert await env.active_conversation(resource, "grp-1", "t2") == t2


@pytest.mark.acceptance(
    spec="channels", scenario="a message to an archived conversation opens a new one"
)
async def test_a_message_to_an_archived_conversation_opens_a_new_one(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel()
    await _say(env, adapter, "first")
    first = await env.active_conversation(resource)
    assert first is not None
    await env.chat.archive_conversation(first)

    await _say(env, adapter, "second")

    second = await env.active_conversation(resource)
    assert second is not None and second != first
    # The archived one is neither revived nor deleted, and nothing was announced.
    assert (await env.chat.get_conversation(first)).archived_at is not None
    assert not any("new conversation" in text for text in adapter.texts())


@pytest.mark.acceptance(spec="channels", scenario="a message with an empty sender id is refused")
async def test_a_message_with_an_empty_sender_id_is_refused(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    adapter = env.bind(resource)
    await env.peers.upsert(
        ChannelPeer(
            resource_uid=resource.uid,
            chat_id="4242",
            display_name="Owner",
            paired_at=datetime.now(tz=UTC),
            sender_id="4242",
        )
    )

    await env.processor.on_message(inbound("tg", "4242", "hello", sender_id=""))

    assert adapter.texts() == []
    peer = await env.peers.get_by_chat(resource.uid, "4242")
    assert peer is not None and peer.sender_id == "4242"


async def test_a_pairing_without_a_sender_id_serves_no_one(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    adapter = env.bind(resource)
    await env.peers.upsert(
        ChannelPeer(
            resource_uid=resource.uid,
            chat_id="4242",
            display_name="Owner",
            paired_at=datetime.now(tz=UTC),
            sender_id="",
        )
    )

    await env.processor.on_message(inbound("tg", "4242", "hello", sender_id="4242"))

    assert adapter.texts() == []
    peer = await env.peers.get_by_chat(resource.uid, "4242")
    assert peer is not None and peer.sender_id == ""
