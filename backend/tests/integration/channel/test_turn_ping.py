"""A long turn ends with one short line where its answer would not notify (spec
channels "Ping the asker when a long turn ends")."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest

from coffer.application.channel.turn_finish import first_line
from coffer.application.channel.turn_render import TurnRenderer
from coffer.domain.chat.events import TextDelta, ToolCall, TurnDone, TurnError

from .conftest import FakeChannelAdapter

_MENTION = '<mention-tag target="seatalk://user?id={user_id}"/>'
_DONE = TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")
_ANSWER = [TextDelta(text="**PR #441** is red on one flaky e2e.\n\nDetails follow."), _DONE]


def _clock(*values: float) -> Callable[[], float]:
    seq = list(values)

    def now() -> float:
        return seq.pop(0) if len(seq) > 1 else seq[0]

    return now


def _streaming(**kwargs: Any) -> FakeChannelAdapter:
    adapter = FakeChannelAdapter(
        supports_edit=False, supports_live_text=True, live_text_persists=True, **kwargs
    )
    adapter.live_text_finalizes = True
    return adapter


async def _run(
    adapter: FakeChannelAdapter,
    events: list[Any],
    *,
    duration: float,
    notify_after: float = 90.0,
    chat_kind: str = "direct",
) -> None:
    async def send(text: str) -> None:
        await adapter.send_text("owner", text, chat_kind=chat_kind)

    renderer = TurnRenderer(
        channel="st",
        adapter=adapter,
        chat_id="owner",
        conversation_id="c1",
        send=send,
        now=_clock(0.0, duration),
        chat_kind=chat_kind,
        mention_user_id="st-77",
        notify_after_seconds=notify_after,
    )
    queue: asyncio.Queue[Any] = asyncio.Queue()
    for event in [*events, None]:
        queue.put_nowait(event)
    await renderer.consume(queue)


@pytest.mark.acceptance(
    spec="channels", scenario="a long turn whose answer does not notify ends with a ping"
)
async def test_a_long_streamed_turn_ends_with_one_done_line() -> None:
    adapter = _streaming()

    await _run(adapter, _ANSWER, duration=252.0)

    # The stream (created at the start) is the answer; the ping is the one new message.
    assert adapter.texts()[1:] == ["✅ Done · 4m 12s — PR #441 is red on one flaky e2e."]


@pytest.mark.acceptance(spec="channels/seatalk", scenario="a group ping mentions the asker")
async def test_a_group_ping_mentions_the_asker_in_the_same_thread() -> None:
    adapter = _streaming(mention_template=_MENTION)

    await _run(adapter, _ANSWER, duration=252.0, chat_kind="group")

    ping = adapter.sent_routed[-1]
    assert ping[1] == (
        '<mention-tag target="seatalk://user?id=st-77"/> '
        "✅ Done · 4m 12s — PR #441 is red on one flaky e2e."
    )
    assert ping[3] == "group"


@pytest.mark.acceptance(spec="channels", scenario="a short turn or a zero threshold sends no ping")
async def test_a_short_turn_and_a_zero_threshold_send_no_ping() -> None:
    short = _streaming()
    await _run(short, _ANSWER, duration=30.0)
    off = _streaming()
    await _run(off, _ANSWER, duration=600.0, notify_after=0)

    assert len(short.texts()) == 1  # the stream's own message only
    assert len(off.texts()) == 1


@pytest.mark.acceptance(spec="channels", scenario="an answer sent as a new message needs no ping")
async def test_an_answer_that_is_a_new_message_gets_no_ping() -> None:
    adapter = FakeChannelAdapter(supports_edit=True)  # scaffolding, like Telegram

    await _run(
        adapter,
        [ToolCall(tool_use_id="t1", tool_name="Bash", tool_input={"command": "ls"}), *_ANSWER],
        duration=600.0,
    )

    assert not any(t.startswith("✅ Done") for t in adapter.texts())


@pytest.mark.acceptance(spec="channels", scenario="a long failed turn pings instead of summarising")
async def test_a_long_failed_turn_pings_once_with_the_summary_facts() -> None:
    adapter = _streaming()

    await _run(
        adapter,
        [
            ToolCall(tool_use_id="t1", tool_name="Bash", tool_input={"command": "ls"}),
            TurnError(code="PROVIDER_TIMEOUT", message="upstream timed out"),
        ],
        duration=125.0,
    )

    after_stream = adapter.texts()[1:]
    assert after_stream == ["⚠️ Failed · 2m 05s · 1 tool — upstream timed out"]


def test_the_first_line_is_read_as_plain_words() -> None:
    assert first_line("## **Deploy** is `green`\nmore") == "Deploy is green"
    assert first_line('<mention-tag target="x"/> - item one') == "item one"
    assert first_line("\n\n```\ncode\n```\nafter") == "code"
    assert len(first_line("x" * 300)) == 120


@pytest.mark.acceptance(spec="channels", scenario="a long turn that waits on the owner pings")
async def test_a_long_turn_ending_on_a_question_pings_needs_you() -> None:
    adapter = _streaming()  # no buttons: the question stays in the streamed reply

    await _run(
        adapter,
        [TextDelta(text="Ready to apply.\n\nNEEDS YOU: Apply to live? (yes / no)"), _DONE],
        duration=200.0,
    )

    assert adapter.texts()[1:] == ["❓ Needs you · 3m 20s — Apply to live?"]
