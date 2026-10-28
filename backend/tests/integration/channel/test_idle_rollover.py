"""A message to a stale conversation opens a new one, and a message with no
sender is refused.

Spec channels "Open a new conversation after an idle period" and "Refuse a
message with an empty sender id".
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from coffer.application.channel.store_ports import ChannelPeer

from .conftest import ChannelEnv, inbound, wait_until

NOTICE = "Started a new conversation"


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
async def test_an_idle_chat_opens_a_new_conversation_silently(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel()
    await _say(env, adapter, "first")
    first = await env.active_conversation(resource)
    assert first is not None
    await _age(env, first, 25)

    await _say(env, adapter, "second")

    second = await env.active_conversation(resource)
    assert second is not None and second != first
    assert not any(NOTICE in text for text in adapter.texts())
    # The old conversation is still there, in the list.
    assert (await env.chat.get_conversation(first)).id == first


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


def _group(thread: str, text: str) -> object:
    return inbound(
        "tg",
        "grp-1",
        text,
        chat_kind="group",
        addressed=True,
        sender_id="owner",
        thread_id=thread,
    )


@pytest.mark.acceptance(
    spec="channels", scenario="a group thread idle past the configured hours keeps its conversation"
)
async def test_a_group_thread_never_rolls_over(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel()
    await env.processor.on_message(_group("t1", "hi"))  # type: ignore[arg-type]
    await wait_until(lambda: adapter.texts().count("Hello world") >= 1)
    t1 = await env.active_conversation(resource, "grp-1", "t1")
    assert t1
    await _age(env, t1, 30)

    await env.processor.on_message(_group("t1", "again"))  # type: ignore[arg-type]
    await wait_until(lambda: adapter.texts().count("Hello world") >= 2)

    assert await env.active_conversation(resource, "grp-1", "t1") == t1
    assert not any(NOTICE in text for text in adapter.texts())


@pytest.mark.acceptance(
    spec="channels", scenario="a group that is one conversation rolls over like a direct chat"
)
async def test_a_group_main_chat_rolls_over(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel()
    await env.processor.on_message(_group("", "hi"))  # type: ignore[arg-type]
    await wait_until(lambda: adapter.texts().count("Hello world") >= 1)
    main = await env.active_conversation(resource, "grp-1", "")
    assert main
    await _age(env, main, 30)

    await env.processor.on_message(_group("", "again"))  # type: ignore[arg-type]
    await wait_until(lambda: adapter.texts().count("Hello world") >= 2)

    assert await env.active_conversation(resource, "grp-1", "") != main
    assert not any(NOTICE in text for text in adapter.texts())


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
