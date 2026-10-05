"""How each platform opens a parallel thread, with the REAL adapter bound into
the real channel core (spec channels/seatalk "Open a parallel thread by posting
its root message", channels/telegram "Open a parallel thread as a private-chat
topic").

Each platform's Open API is its in-process fake, so what is asserted is the wire
traffic the platform would receive and the conversation the owner's next
message lands in.
"""

from __future__ import annotations

from typing import Any

import pytest

from coffer.application.channel.ports import AdapterCallbacks
from coffer.infrastructure.channel.telegram_topics import TOPICS_OFF
from tests.integration.infrastructure.channel.conftest import (
    FakeSeaTalk,
    FakeTelegram,
    make_seatalk_adapter,
    make_telegram_adapter,
)

from .conftest import DEFAULT_AGENT_KEY, ChannelEnv, wait_until

_OWNER_ID = 4242


def _callbacks(env: ChannelEnv) -> AdapterCallbacks:
    return AdapterCallbacks(
        on_message=env.processor.on_message,
        on_callback=env.processor.on_callback,
        on_lifecycle=env.processor.on_lifecycle,
        on_stop=env.processor.on_stop,
    )


async def _user_texts(env: ChannelEnv, conversation_id: str) -> list[str]:
    return env.user_texts(conversation_id)


# -- SeaTalk -------------------------------------------------------------------


def _seatalk_dm(text: str, *, message_id: str, thread_id: str = "") -> dict[str, Any]:
    return {
        "event_id": f"evt-{message_id}",
        "event_type": "message_from_bot_subscriber",
        "timestamp": 1771000000,
        "event": {
            "employee_code": "emp-1",
            "email": "owner@example.com",
            "message": {
                "message_id": message_id,
                "thread_id": thread_id,
                "tag": "text",
                "text": {"content": text},
            },
        },
    }


@pytest.mark.acceptance(
    spec="channels/seatalk", scenario="/thread posts the root message the thread hangs from"
)
async def test_seatalk_thread_posts_the_root_message_the_thread_hangs_from(
    env: ChannelEnv,
) -> None:
    env.keyring.set("channel/st/app-secret", "app-secret-value")
    resource = await env.resources.register(
        kind="channel",
        name="st",
        config={
            "channel_type": "seatalk",
            "app_id": "app-1",
            "app_secret_ref": "channel/st/app-secret",
            "default_agent": await env.agent_uid(DEFAULT_AGENT_KEY),
        },
        actor="test",
    )
    fake = FakeSeaTalk()
    adapter = make_seatalk_adapter(fake)
    env.bind(resource, adapter)  # type: ignore[arg-type]
    await env.pair(resource, "emp-1", sender_id="emp-1")
    await adapter.start(_callbacks(env))
    try:
        await adapter.handle_event(_seatalk_dm("/thread", message_id="u-1"))
        [root] = [body["message"] for body, _auth in fake.single_chat_calls]
        # A new direct-chat message (no thread of its own) opening with the mark.
        assert root["tag"] == "text"
        assert not root.get("thread_id")
        assert root["text"]["content"].startswith("🧵#1 Task")
        root_id = "m1"  # the fake's first single_chat message id

        # A reply under that message drives the new parallel conversation.
        await adapter.handle_event(
            _seatalk_dm("what is left?", message_id="u-2", thread_id=root_id)
        )
        parallel = await env.active_conversation(resource, "emp-1", root_id)
        assert parallel is not None
        await wait_until(lambda: _user_texts(env, parallel))
        assert await _user_texts(env, parallel) == ["what is left?"]
        assert (await env.chat.get_conversation(parallel)).title == "🧵#1 Task"
        # It did not fold into the direct chat's conversation.
        assert await env.active_conversation(resource, "emp-1") is None
    finally:
        await adapter.stop()


# -- Telegram ------------------------------------------------------------------


async def _telegram(env: ChannelEnv, fake: FakeTelegram) -> tuple[Any, Any]:
    fake.results["getMe"] = {"id": 999, "username": "mybot"}
    resource = await env.register_channel()
    adapter = make_telegram_adapter(fake)
    env.bind(resource, adapter)  # type: ignore[arg-type]
    await env.pair(resource, str(_OWNER_ID), sender_id=str(_OWNER_ID))
    await adapter.start(_callbacks(env))
    return resource, adapter


def _private(update_id: int, text: str, **extra: Any) -> dict[str, Any]:
    message: dict[str, Any] = {
        "message_id": 10 + update_id,
        "date": 1718000000,
        "chat": {"id": _OWNER_ID, "type": "private"},
        "from": {"id": _OWNER_ID, "first_name": "Yu"},
        "text": text,
    }
    message.update(extra)
    return {"update_id": update_id, "message": message}


def _sent(fake: FakeTelegram) -> list[dict[str, Any]]:
    return fake.calls_for("sendMessage")


@pytest.mark.acceptance(
    spec="channels/telegram", scenario="/thread creates a named private-chat topic"
)
async def test_telegram_thread_creates_a_named_private_chat_topic(env: ChannelEnv) -> None:
    fake = FakeTelegram()
    fake.results["createForumTopic"] = {"message_thread_id": 77, "name": "🧵#1 deploy check"}
    resource, adapter = await _telegram(env, fake)
    try:
        await fake.update_batches.put([_private(1, "/thread deploy check")])
        await wait_until(lambda: any(p.get("message_thread_id") == 77 for p in _sent(fake)))
        [created] = fake.calls_for("createForumTopic")
        assert created["name"] == "🧵#1 deploy check"
        assert str(created["chat_id"]) == str(_OWNER_ID)
        [header] = [p for p in _sent(fake) if p.get("message_thread_id") == 77]
        assert "🧵#1 deploy check" in header["text"]

        # Messages in that topic run in their own conversation.
        await fake.update_batches.put([_private(2, "hi", message_thread_id=77)])
        await wait_until(lambda: env.active_conversation(resource, str(_OWNER_ID), "77"))
        topic = await env.active_conversation(resource, str(_OWNER_ID), "77")
        assert topic is not None
        assert (await env.chat.get_conversation(topic)).title == "🧵#1 deploy check"
        await wait_until(lambda: _user_texts(env, topic))
        assert await _user_texts(env, topic) == ["hi"]
        assert await env.active_conversation(resource, str(_OWNER_ID)) is None
    finally:
        await adapter.stop()


@pytest.mark.acceptance(
    spec="channels/telegram", scenario="/thread explains how to enable topics when they are off"
)
async def test_telegram_thread_explains_how_to_enable_topics(env: ChannelEnv) -> None:
    fake = FakeTelegram()
    fake.refusals["createForumTopic"] = "Bad Request: the chat is not a forum"
    resource, adapter = await _telegram(env, fake)
    try:
        await fake.update_batches.put([_private(1, "/thread")])
        await wait_until(lambda: any("Threaded Mode" in str(p.get("text")) for p in _sent(fake)))
    finally:
        await adapter.stop()
    [answer] = [p for p in _sent(fake) if "Threaded Mode" in str(p.get("text"))]
    assert "BotFather" in answer["text"]
    assert "message_thread_id" not in answer
    assert TOPICS_OFF.startswith("Telegram topics are off")
    # Nothing was created or recorded.
    assert await env.threads.list_parallel(resource.uid, str(_OWNER_ID)) == []
