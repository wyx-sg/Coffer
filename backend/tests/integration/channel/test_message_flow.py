"""Paired messages drive real chat-platform turns; replies land in the IM chat.

The chat side is the REAL ChatService + TurnOrchestrator over real SQLite;
only the agent is scripted (FakeAgentAdapter) and only the transport is the
recording FakeChannelAdapter.
"""

from __future__ import annotations

import pytest

from coffer.domain.chat.events import TextDelta, TurnDone, TurnError, TurnStarted
from coffer.domain.chat.message import Role, TextBlock
from tests.unit.chat.conftest import FakeAgentAdapter

from .conftest import ChannelEnv, inbound, wait_until


def _text(message) -> str:  # type: ignore[no-untyped-def]
    return "".join(b.text for b in message.content if isinstance(b, TextBlock))


@pytest.mark.acceptance(spec="009-channels", scenario="a paired message gets an agent reply")
async def test_paired_message_runs_a_turn_and_delivers_the_reply(env: ChannelEnv) -> None:
    env.provider.adapter = FakeAgentAdapter(
        [
            TurnStarted(),
            TextDelta(text="Hello "),
            TextDelta(text="world"),
            TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
        ]
    )
    resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "hi"))
    await wait_until(lambda: "Hello world" in adapter.texts())

    assert ("owner", "Hello world") in adapter.sent
    assert adapter.typing == ["owner"]  # typing ack before the turn

    conversations = await env.chat.list_conversations()
    assert len(conversations) == 1
    assert await env.active_conversation(resource) == conversations[0].id

    messages = await env.chat.list_messages(conversations[0].id)
    assert [(m.role, _text(m)) for m in messages] == [
        (Role.USER, "hi"),
        (Role.ASSISTANT, "Hello world"),
    ]
    assert all(m.status == "complete" for m in messages)


@pytest.mark.acceptance(
    spec="009-channels", scenario="the channel conversation is a normal chat conversation"
)
async def test_channel_conversation_appears_in_the_chat_platform_apis(env: ChannelEnv) -> None:
    env.provider.adapter = FakeAgentAdapter(
        [
            TurnStarted(),
            TextDelta(text="42"),
            TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
        ]
    )
    _resource, adapter = await env.paired_channel()
    await env.processor.on_message(inbound("tg", "owner", "meaning of life?"))
    await wait_until(lambda: "42" in adapter.texts())

    # The conversation is listed and readable like any web-UI conversation.
    conversations = await env.chat.list_conversations()
    assert len(conversations) == 1
    conversation = await env.chat.get_conversation(conversations[0].id)
    assert conversation.agent_key == "builtin"

    messages = await env.chat.list_messages(conversation.id)
    assert [m.role for m in messages] == [Role.USER, Role.ASSISTANT]
    assert _text(messages[0]) == "meaning of life?"
    assert _text(messages[1]) == "42"


@pytest.mark.acceptance(spec="009-channels", scenario="a turn error is reported to the IM chat")
async def test_turn_error_is_delivered_as_a_short_notice(env: ChannelEnv) -> None:
    env.provider.adapter = FakeAgentAdapter(
        [TurnStarted(), TurnError(code="PROVIDER_TIMEOUT", message="upstream timed out")]
    )
    _resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "hi"))
    await wait_until(lambda: any(t.startswith("⚠️") for t in adapter.texts()))

    notice = next(t for t in adapter.texts() if t.startswith("⚠️"))
    assert "upstream timed out" in notice
    assert "PROVIDER_TIMEOUT" in notice
    # The channel stays up: the binding is still live and answers commands.
    assert env.processor.binding("tg") is not None


async def test_empty_message_with_no_attachments_gets_an_unsupported_notice(
    env: ChannelEnv,
) -> None:
    # A blank envelope with nothing downloadable (a sticker, a location) — a
    # photo or file WOULD drive a turn, but there is nothing here.
    _resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "   "))

    assert adapter.texts() == ["⚠️ Unsupported message — send text, a photo, or a file."]
    assert await env.chat.list_conversations() == []


async def test_unknown_command_gets_a_pointer_at_help(env: ChannelEnv) -> None:
    _resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/frobnicate now"))

    assert adapter.texts() == ["Unknown command /frobnicate. /help"]


async def test_help_lists_the_channel_commands(env: ChannelEnv) -> None:
    _resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/help"))

    assert len(adapter.texts()) == 1
    help_text = adapter.texts()[0]
    for command in ("/new", "/stop", "/status", "/help"):
        assert command in help_text


async def test_status_reports_conversation_agent_and_queue(env: ChannelEnv) -> None:
    _resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/status"))

    assert len(adapter.texts()) == 1
    status = adapter.texts()[0]
    assert "Conversation: none yet" in status
    assert "Agent: builtin" in status
    assert "Turn running: no" in status
    assert "Queued: 0" in status


async def test_dangling_active_conversation_is_recreated_on_next_message(
    env: ChannelEnv,
) -> None:
    resource, adapter = await env.paired_channel()

    # On this edit-capable adapter a clean success emits just the reply — the
    # trailing fact summary is suppressed, so one text marks a finished turn.
    await env.processor.on_message(inbound("tg", "owner", "first"))
    await wait_until(lambda: len(adapter.texts()) >= 1)
    old_conversation = await env.active_conversation(resource)
    assert old_conversation is not None

    # The user deletes the conversation from the web UI.
    await env.chat.delete_conversation(old_conversation, actor="user")

    await env.processor.on_message(inbound("tg", "owner", "second"))
    await wait_until(lambda: len(adapter.texts()) >= 2)

    fresh = await env.active_conversation(resource)
    assert fresh is not None
    assert fresh != old_conversation
    messages = await env.chat.list_messages(fresh)
    assert _text(messages[0]) == "second"
