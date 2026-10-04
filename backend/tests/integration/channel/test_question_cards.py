"""A question the agent asks the owner goes out as a card in the chat and its
answer goes back to the agent (spec channels "Ask the owner in the chat and take
the answer back to the agent").

A real turn orchestrator runs a scripted agent that asks through the function the
Claude Code hook and ``coffer__ask`` share; the channel renders the turn's events,
the owner taps or types, and the web answers through ``answer_question``.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Iterator
from typing import Any

import pytest

from coffer.application.chat import questions
from coffer.application.chat.questions import AnswerInput
from coffer.domain.chat.message import TextBlock
from tests.unit.chat.test_questions import TWO, YES_NO, AskingAdapter

from .conftest import ChannelEnv, FakeChannelAdapter, inbound, tap_event, turn_body, wait_until

_OWNER = "owner-1"
_TIME = r"\d\d:\d\d"


@pytest.fixture(autouse=True)
def _clean_questions() -> Iterator[None]:
    questions.clear_all()
    yield
    questions.clear_all()


def _asking(env: ChannelEnv, ask_input: dict[str, Any]) -> list[AskingAdapter]:
    built: list[AskingAdapter] = []

    async def build(conversation_id: str) -> AskingAdapter:
        adapter = AskingAdapter(conversation_id, ask_input, as_tool="AskUserQuestion")
        built.append(adapter)
        return adapter

    env.provider.build_adapter = build  # type: ignore[method-assign]
    return built


async def _chat(
    env: ChannelEnv, ask_input: dict[str, Any], **adapter_kwargs: Any
) -> tuple[Any, FakeChannelAdapter, list[AskingAdapter]]:
    built = _asking(env, ask_input)
    resource = await env.register_channel()
    adapter = env.bind(
        resource,
        FakeChannelAdapter(supports_buttons=True, supports_card_update=True, **adapter_kwargs),
    )
    await env.pair(resource, "owner", sender_id=_OWNER)
    await env.processor.on_message(inbound("tg", "owner", "go", sender_id=_OWNER))
    await wait_until(lambda: bool(adapter.cards))
    return resource, adapter, built


async def _tap(env: ChannelEnv, data: str, **kwargs: Any) -> None:
    await env.processor.on_callback(tap_event("tg", "owner", data, sender_id=_OWNER, **kwargs))


def _user_texts(env: ChannelEnv, conversation_id: str) -> Any:
    async def read() -> list[str]:
        messages = await env.chat.list_messages(conversation_id)
        return [
            turn_body("".join(b.text for b in m.content if isinstance(b, TextBlock)))
            for m in messages
            if m.role.value == "user"
        ]

    return read()


def _qid(conversation_id: str) -> str:
    block = questions.pending_question_for(conversation_id)
    assert block is not None
    return block.question_id


@pytest.mark.acceptance(
    spec="channels", scenario="a tap answers the agent without a message from the owner"
)
async def test_a_tap_answers_the_agent_and_rewrites_the_card_without_a_message(
    env: ChannelEnv,
) -> None:
    resource, adapter, built = await _chat(env, YES_NO)
    conversation_id = await env.active_conversation(resource)
    assert conversation_id is not None

    [(_chat_id, text, buttons)] = adapter.cards
    assert text == (
        "❓ Apply this change to staging?\n\n• Yes\n• No — Keep it local\n\n"
        "Or reply with your answer."
    )
    assert [b.label for b in buttons] == ["Yes", "No"]
    assert all(b.own_row for b in buttons)

    await _tap(env, buttons[0].value, platform_message_id="m1")
    await wait_until(lambda: built[0].outcome is not None)

    outcome = built[0].outcome
    assert outcome is not None and outcome.answered
    assert [a.display() for a in outcome.block.answers] == ["Yes"]
    assert outcome.block.answered_via == env.processor.binding(resource.uid).resource.uid  # type: ignore[union-attr]
    [(_c, _mid, closed, closed_buttons, _t)] = adapter.card_updates
    assert re.fullmatch(rf"Apply this change to staging\?\n\n✓ Answered: Yes · {_TIME}", closed)
    assert closed_buttons == []
    # Nothing was posted as the owner: the only user message is the first one.
    await wait_until(lambda: not questions.needs_you(conversation_id))
    assert await _user_texts(env, conversation_id) == ["go"]


@pytest.mark.acceptance(spec="channels", scenario="a text reply answers the pending question")
async def test_a_text_message_is_the_answer_and_starts_no_turn(env: ChannelEnv) -> None:
    resource, adapter, built = await _chat(env, YES_NO)
    conversation_id = await env.active_conversation(resource)
    assert conversation_id is not None

    await env.processor.on_message(
        inbound(
            "tg", "owner", "only the read replica", sender_id=_OWNER, platform_message_id="pm-2"
        )
    )
    await wait_until(lambda: built[0].outcome is not None)

    outcome = built[0].outcome
    assert outcome is not None
    [answer] = outcome.block.answers
    assert (answer.selected, answer.text) == ((), "only the read replica")
    assert env.orchestrator.pending(conversation_id) == []
    await wait_until(lambda: bool(adapter.card_updates))
    assert re.search(rf"✓ Answered: only the read replica · {_TIME}$", adapter.card_updates[0][2])
    assert await _user_texts(env, conversation_id) == ["go"]


@pytest.mark.acceptance(
    spec="channels", scenario="an answer given in Coffer rewrites the chat card"
)
async def test_an_answer_given_in_coffer_rewrites_the_card(env: ChannelEnv) -> None:
    resource, adapter, _built = await _chat(env, YES_NO)
    conversation_id = await env.active_conversation(resource)
    assert conversation_id is not None

    await questions.answer_question(
        conversation_id,
        _qid(conversation_id),
        [AnswerInput(selected=["Yes"])],
        via="web",
        by="Alex",
    )
    await wait_until(lambda: bool(adapter.card_updates))

    assert re.search(rf"✓ Answered in Coffer: Yes · {_TIME}$", adapter.card_updates[0][2])
    assert adapter.card_updates[0][3] == []


@pytest.mark.acceptance(spec="channels", scenario="several questions go out one card at a time")
@pytest.mark.acceptance(
    spec="channels", scenario="a multi-select question is answered with Submit in the chat"
)
async def test_several_questions_go_out_in_order_and_multi_select_submits(
    env: ChannelEnv,
) -> None:
    resource, adapter, built = await _chat(env, TWO)
    conversation_id = await env.active_conversation(resource)
    assert conversation_id is not None
    [(_c, first, first_buttons)] = adapter.cards
    assert first.startswith("```diff\n- a\n+ b\n```\n\n❓ Which environment?")

    await _tap(env, first_buttons[0].value, platform_message_id="m1")
    await wait_until(lambda: len(adapter.cards) == 2)
    # The first card is rewritten before the second goes out; the context is not repeated.
    assert adapter.card_updates[0][2].endswith(
        "✓ Answered: staging · " + adapter.card_updates[0][2][-5:]
    )
    _c, second, second_buttons = adapter.cards[1]
    assert second.startswith("❓ Which parts?")
    assert [b.label for b in second_buttons] == ["api", "web", "docs", "Submit"]

    # Submit with nothing ticked does nothing.
    await _tap(env, second_buttons[3].value, platform_message_id="m2")
    assert questions.pending_question_for(conversation_id) is not None

    await _tap(env, second_buttons[0].value, platform_message_id="m2")
    await _tap(env, second_buttons[2].value, platform_message_id="m2")
    ticked = adapter.card_updates[-1][3]
    assert [b.label for b in ticked] == ["✓ api", "web", "✓ docs", "Submit"]
    assert built[0].outcome is None

    await _tap(env, second_buttons[3].value, platform_message_id="m2")
    await wait_until(lambda: built[0].outcome is not None)
    outcome = built[0].outcome
    assert outcome is not None
    assert [a.display() for a in outcome.block.answers] == ["staging", "api, docs"]
    await wait_until(lambda: len(adapter.card_updates) >= 4)
    assert re.search(rf"✓ Answered: api, docs · {_TIME}$", adapter.card_updates[-1][2])


@pytest.mark.acceptance(spec="channels", scenario="a non-owner's tap is refused")
async def test_a_tap_from_someone_else_in_the_group_is_refused(env: ChannelEnv) -> None:
    built = _asking(env, YES_NO)
    resource = await env.register_channel()
    adapter = env.bind(
        resource, FakeChannelAdapter(supports_buttons=True, supports_card_update=True)
    )
    await env.pair(resource, "owner", sender_id=_OWNER)
    await env.processor.on_message(
        inbound("tg", "grp-1", "@bot go", chat_kind="group", sender_id=_OWNER, thread_id="t1")
    )
    await wait_until(lambda: bool(adapter.cards))
    conversation_id = (await env.chat.list_conversations())[0].id

    await env.processor.on_callback(
        tap_event(
            "tg",
            "grp-1",
            adapter.cards[0][2][0].value,
            sender_id="intruder",
            chat_kind="group",
            thread_id="t1",
        )
    )

    assert any("owners can use it here" in t for t in adapter.texts())
    assert questions.pending_question_for(conversation_id) is not None
    assert built[0].outcome is None


@pytest.mark.acceptance(spec="channels", scenario="stopping a turn rewrites the pending card")
async def test_stopping_the_turn_rewrites_the_card_to_stopped(env: ChannelEnv) -> None:
    _resource, adapter, _built = await _chat(env, YES_NO)

    await env.processor.on_message(inbound("tg", "owner", "/stop", sender_id=_OWNER))
    await wait_until(lambda: bool(adapter.card_updates))

    assert adapter.card_updates[0][2].endswith("⏹ Stopped")
    assert adapter.card_updates[0][3] == []


async def test_a_tap_on_a_retired_reply_button_does_nothing(env: ChannelEnv) -> None:
    resource, adapter, _built = await _chat(env, YES_NO)
    conversation_id = await env.active_conversation(resource)
    assert conversation_id is not None

    await _tap(env, "reply:yes", platform_message_id="m1")
    await asyncio.sleep(0.05)

    assert questions.pending_question_for(conversation_id) is not None
    assert adapter.card_updates == []
    assert await _user_texts(env, conversation_id) == ["go"]
