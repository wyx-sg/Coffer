"""A question the agent ends on becomes buttons; a tap is the owner's own reply
(spec channels "Turn a question for the owner into buttons")."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from coffer.application.channel.turn_render import TurnRenderer
from coffer.domain.chat.events import TextDelta, TurnDone, TurnStarted
from coffer.domain.chat.message import TextBlock
from tests.unit.chat.conftest import FakeAgentAdapter

from .conftest import ChannelEnv, FakeChannelAdapter, inbound, tap_event, turn_body, wait_until

_PREVIEW = "Will set `timeout: 30s` on checkout-live.\n\nNEEDS YOU: Apply this change? (yes / no)"
_DONE = TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")


def _asking(reply: str = _PREVIEW) -> FakeAgentAdapter:
    return FakeAgentAdapter([TurnStarted(), TextDelta(text=reply), _DONE])


async def _render(adapter: FakeChannelAdapter) -> str:
    cards: list[tuple[str, list[Any]]] = []

    async def send(text: str) -> None:
        await adapter.send_text("owner", text)

    async def send_card(text: str, buttons: Any) -> None:
        cards.append((text, list(buttons)))
        await adapter.send_text("owner", text, buttons=buttons)

    renderer = TurnRenderer(
        channel="tg",
        adapter=adapter,
        chat_id="owner",
        conversation_id="c1",
        send=send,
        send_card=send_card,
        now=lambda: 0.0,
    )
    queue: asyncio.Queue[Any] = asyncio.Queue()
    for event in [TextDelta(text=_PREVIEW), _DONE, None]:
        queue.put_nowait(event)
    return await renderer.consume(queue)


@pytest.mark.acceptance(spec="channels", scenario="a question the agent ends on becomes buttons")
async def test_the_question_follows_the_answer_with_one_button_per_option() -> None:
    adapter = FakeChannelAdapter(supports_edit=False, supports_buttons=True)

    outcome = await _render(adapter)

    assert outcome == "waiting"
    assert adapter.texts() == [
        "Will set `timeout: 30s` on checkout-live.",
        "❓ Apply this change?",
    ]
    [(_chat, _text, buttons)] = adapter.cards
    assert [(b.label, b.value) for b in buttons] == [("yes", "reply:yes"), ("no", "reply:no")]


async def test_without_buttons_the_question_stays_in_the_reply() -> None:
    adapter = FakeChannelAdapter(supports_edit=False)

    await _render(adapter)

    assert adapter.texts() == [
        "Will set `timeout: 30s` on checkout-live.\n\n❓ Apply this change? (yes / no)"
    ]


def _text(message: object) -> str:
    return "".join(b.text for b in message.content if isinstance(b, TextBlock))  # type: ignore[attr-defined]


@pytest.mark.acceptance(spec="channels", scenario="a tap is sent as the owner's own reply")
async def test_the_owners_tap_enters_the_conversation_as_their_reply(env: ChannelEnv) -> None:
    env.provider.adapter = _asking()
    resource = await env.register_channel()
    adapter = env.bind(
        resource, FakeChannelAdapter(supports_buttons=True, supports_card_update=True)
    )
    await env.pair(resource, "owner", sender_id="owner-1")

    await env.processor.on_message(inbound("tg", "owner", "set the timeout", sender_id="owner-1"))
    await wait_until(lambda: bool(adapter.cards))
    await env.processor.on_callback(
        tap_event("tg", "owner", "reply:yes", sender_id="owner-1", platform_message_id="m9")
    )
    conversation_id = await env.active_conversation(resource)
    assert conversation_id is not None

    async def _user_texts() -> list[str]:
        messages = await env.chat.list_messages(conversation_id)
        return [turn_body(_text(m)) for m in messages if m.role.value == "user"]

    for _ in range(200):
        if await _user_texts() == ["set the timeout", "yes"]:
            break
        await asyncio.sleep(0.02)
    assert await _user_texts() == ["set the timeout", "yes"]
    # The card now shows the answer and offers nothing more to tap.
    [(_chat, message_id, text, buttons, _title)] = adapter.card_updates
    assert (message_id, text) == ("m9", "Answered: yes")
    assert [b.selected for b in buttons] == [True]


@pytest.mark.acceptance(spec="channels", scenario="a non-owner's tap is refused")
async def test_a_tap_from_someone_else_in_the_group_is_refused(env: ChannelEnv) -> None:
    env.provider.adapter = _asking()
    resource = await env.register_channel()
    adapter = env.bind(resource, FakeChannelAdapter(supports_buttons=True, supports_groups=True))
    await env.pair(resource, "owner", sender_id="owner-1")
    await env.processor.on_message(
        inbound("tg", "grp-1", "@bot go", chat_kind="group", sender_id="owner-1", thread_id="t1")
    )
    await wait_until(lambda: bool(adapter.cards))
    before = len(await env.chat.list_conversations())

    await env.processor.on_callback(
        tap_event(
            "tg", "grp-1", "reply:yes", sender_id="intruder", chat_kind="group", thread_id="t1"
        )
    )

    assert any("Not authorized" in t for t in adapter.texts())
    conversations = await env.chat.list_conversations()
    assert len(conversations) == before
    messages = await env.chat.list_messages(conversations[0].id)
    assert [turn_body(_text(m)) for m in messages if m.role.value == "user"] == ["@bot go"]
