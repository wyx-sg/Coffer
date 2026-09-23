"""A real TelegramAdapter, polling a fake Bot API, wired into the channel core.

The adapter-level tests prove what the transport puts on the wire; these prove
what happens once the core acts on it — a stop press reaching the interrupt
path, a group command answered privately, a forum-topic turn answered in its
topic. The Bot API is an in-process fake; nothing leaves the machine.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from coffer.application.channel.ports import AdapterCallbacks
from coffer.application.chat.turn_orchestrator import active_turns
from coffer.domain.errors import CredentialMissing
from coffer.infrastructure.channel.telegram import TelegramAdapter
from tests.integration.infrastructure.channel.conftest import (
    FakeTelegram,
    make_telegram_adapter,
)

from .conftest import ChannelEnv, wait_until
from .test_queue_and_stop import GatedAdapter

_BOT_ID = 999
_OWNER_ID = 4242
_GROUP_ID = -100123


async def _telegram_channel(
    env: ChannelEnv, fake: FakeTelegram, *, owner_chat: str
) -> tuple[Any, TelegramAdapter]:
    """A registered telegram channel whose binding is a REAL adapter, polling
    ``fake`` and feeding the channel core, with the owner paired."""
    fake.results["getMe"] = {"id": _BOT_ID, "username": "mybot"}
    resource = await env.register_channel()
    adapter = make_telegram_adapter(fake)
    env.bind(resource, adapter)  # type: ignore[arg-type]
    await env.pair(resource, owner_chat, sender_id=str(_OWNER_ID))
    await adapter.start(
        AdapterCallbacks(
            on_message=env.processor.on_message,
            on_callback=env.processor.on_callback,
            on_lifecycle=env.processor.on_lifecycle,
            on_stop=env.processor.on_stop,
        )
    )
    return resource, adapter


def _group_message(update_id: int, text: str, **extra: Any) -> dict[str, Any]:
    message: dict[str, Any] = {
        "message_id": 5000 + update_id,
        "date": 1718000000,
        "chat": {"id": _GROUP_ID, "type": "supergroup", "title": "Team"},
        "from": {"id": _OWNER_ID, "first_name": "Yu"},
        "text": text,
    }
    message.update(extra)
    return {"update_id": update_id, "message": message}


def _sent_texts(fake: FakeTelegram) -> list[str]:
    return [
        str(p.get("text") or (p.get("rich_message") or {}).get("markdown") or "")
        for m, p in fake.calls
        if m in ("sendMessage", "sendRichMessage")
    ]


@pytest.mark.acceptance(
    spec="channels/telegram", scenario="pressing the draft's stop button interrupts the turn"
)
async def test_the_drafts_stop_button_interrupts_the_running_turn(env: ChannelEnv) -> None:
    fake = FakeTelegram()
    fake.supports_drafts = True
    gated = GatedAdapter()
    env.provider.adapter = gated
    resource, adapter = await _telegram_channel(env, fake, owner_chat=str(_OWNER_ID))
    try:
        await fake.update_batches.put(
            [
                {
                    "update_id": 1,
                    "message": {
                        "message_id": 10,
                        "date": 1718000000,
                        "chat": {"id": _OWNER_ID, "type": "private"},
                        "from": {"id": _OWNER_ID, "first_name": "Yu"},
                        "text": "long job",
                    },
                }
            ]
        )
        await asyncio.wait_for(gated.entered.wait(), timeout=5.0)
        conversation_id = await env.active_conversation(resource, str(_OWNER_ID))
        assert conversation_id is not None
        assert conversation_id in active_turns()

        # The platform reports the user pressed the stop button it drew on the
        # streamed draft — no text was typed.
        await fake.update_batches.put(
            [
                {
                    "update_id": 2,
                    "stopped_message_generation": {
                        "chat": {"id": _OWNER_ID, "type": "private"},
                        "draft_id": 1,
                    },
                }
            ]
        )
        # The same outcome a typed /stop produces: the turn is cancelled and the
        # chat hears the same acknowledgement.
        await wait_until(lambda: conversation_id not in active_turns())
        await wait_until(lambda: any("Stopped." in t for t in _sent_texts(fake)))
        assert any("Stopping" in t for t in _sent_texts(fake))
        assert not any("echo:" in t for t in _sent_texts(fake))
    finally:
        gated.release.set()
        await adapter.stop()


@pytest.mark.acceptance(
    spec="channels/telegram",
    scenario="a group command answer is sent as an ephemeral message to the asker",
)
async def test_a_group_command_answer_goes_to_the_asker_alone(env: ChannelEnv) -> None:
    fake = FakeTelegram()
    env.add_agent("codex")
    _resource, adapter = await _telegram_channel(env, fake, owner_chat=str(_OWNER_ID))
    mention = [{"type": "mention", "offset": 0, "length": len("@mybot")}]
    try:
        # The owner sent /status as an ephemeral command, which is what gives
        # the bot an ephemeral_message_id to answer privately against.
        await fake.update_batches.put(
            [_group_message(1, "@mybot /status", entities=mention, ephemeral_message_id=77)]
        )
        await wait_until(lambda: len(fake.calls_for("sendMessage")) >= 1)
        status = fake.calls_for("sendMessage")[0]
        assert status["chat_id"] == str(_GROUP_ID)
        assert status["ephemeral_message_parameters"] == {"receiver_user_id": _OWNER_ID}
        assert status["reply_parameters"]["ephemeral_message_id"] == 77
        assert "Conversation" in status["text"] or "conversation" in status["text"]

        # /agent with no argument renders a selection card in the same group.
        await fake.update_batches.put(
            [_group_message(2, "@mybot /agent", entities=mention, ephemeral_message_id=78)]
        )

        def _card() -> dict[str, Any] | None:
            for method, params in fake.calls:
                if method in ("sendMessage", "sendRichMessage") and "reply_markup" in params:
                    return params
            return None

        await wait_until(lambda: _card() is not None)
        card = _card()
        assert card is not None
        # A card must be rewritable after the tap, so it stays an ordinary
        # message: no ephemeral addressing at all.
        assert "ephemeral_message_parameters" not in card
    finally:
        await adapter.stop()


@pytest.mark.acceptance(
    spec="channels/telegram",
    scenario="a mention in a forum topic is answered in that topic without reading history",
)
async def test_a_forum_topic_mention_is_answered_in_the_topic(env: ChannelEnv) -> None:
    fake = FakeTelegram()
    resource, adapter = await _telegram_channel(env, fake, owner_chat=str(_OWNER_ID))
    history_reads: list[tuple[Any, ...]] = []
    real_fetch = adapter.fetch_thread

    async def spy_fetch(*args: Any, **kwargs: Any) -> Any:
        history_reads.append(args)
        return await real_fetch(*args, **kwargs)

    adapter.fetch_thread = spy_fetch  # type: ignore[method-assign]
    mention = [{"type": "mention", "offset": 0, "length": len("@mybot")}]
    try:
        await fake.update_batches.put(
            [
                _group_message(
                    1,
                    "@mybot what is up",
                    entities=mention,
                    message_thread_id=9,
                    is_topic_message=True,
                )
            ]
        )
        await wait_until(lambda: any("Hello world" in t for t in _sent_texts(fake)), timeout=8.0)
    finally:
        await adapter.stop()

    replies = [
        p
        for m, p in fake.calls
        if m in ("sendMessage", "sendRichMessage")
        and "Hello world"
        in str(p.get("text") or (p.get("rich_message") or {}).get("markdown") or "")
    ]
    assert replies
    assert all(int(p["message_thread_id"]) == 9 for p in replies)
    assert all(str(p["chat_id"]) == str(_GROUP_ID) for p in replies)
    # No thread history is read: the core never asks the transport for it, and
    # nothing that reads messages is sent to the Bot API.
    assert history_reads == []
    readers = {"getChatHistory", "getMessages", "forwardMessages", "copyMessages"}
    assert not {m for m, _ in fake.calls} & readers
    assert resource.id


@pytest.mark.acceptance(
    spec="channels/telegram",
    scenario="register a telegram channel whose token reference resolves",
)
async def test_a_telegram_channel_stores_the_token_reference_only(env: ChannelEnv) -> None:
    token = "123456:SECRET-bot-token"
    env.keyring.set("channel/tg/bot-token", token)
    created = await env.resources.register(
        kind="channel",
        name="tg",
        config={"channel_type": "telegram", "bot_token_ref": "channel/tg/bot-token"},
        actor="cli",
    )
    [listed] = await env.resources.list(kind="channel")
    assert listed.id == created.id
    assert listed.config["bot_token_ref"] == "channel/tg/bot-token"
    # The token itself lives in the credential store, never in the config.
    assert token not in repr(listed.config)

    with pytest.raises(CredentialMissing):
        await env.resources.register(
            kind="channel",
            name="tg2",
            config={"channel_type": "telegram", "bot_token_ref": "channel/tg2/missing"},
            actor="cli",
        )
    assert [r.name for r in await env.resources.list(kind="channel")] == ["tg"]
