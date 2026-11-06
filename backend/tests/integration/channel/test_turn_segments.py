"""Text written on either side of a tool call is two segments, not one run-on.

An agent streams "Let me check the logs." — runs a tool — then "The failure is…".
Both arrive as bare ``TextDelta``s, so a renderer that only concatenated them
would deliver "…check the logs.The failure is…". The tool call between them is
the boundary: the text before it is narration and the final reply is the text
after it alone (spec channels "Send only the answer, once the turn is done").
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from coffer.application.channel.turn_render import TurnRenderer
from coffer.domain.chat.events import TextDelta, ToolCall, ToolResult, TurnDone

from .conftest import FakeChannelAdapter


async def _render(adapter: FakeChannelAdapter, events: list[Any]) -> None:
    async def send(text: str) -> None:
        await adapter.send_text("owner", text)

    renderer = TurnRenderer(
        channel="tg",
        adapter=adapter,
        chat_id="owner",
        conversation_id="c1",
        send=send,
        now=lambda: 0.0,
    )
    queue: asyncio.Queue[Any] = asyncio.Queue()
    for event in [*events, None]:
        queue.put_nowait(event)
    await renderer.consume(queue)


async def test_only_the_text_after_the_tool_call_is_the_reply() -> None:
    adapter = FakeChannelAdapter()

    await _render(
        adapter,
        [
            TextDelta(text="Let me check "),
            TextDelta(text="the logs."),
            ToolCall(tool_use_id="t1", tool_name="Bash", tool_input={"command": "tail log"}),
            ToolResult(tool_use_id="t1", tool_name="Bash", output="ok", error=None),
            TextDelta(text="The failure is "),
            TextDelta(text="the 3DS step."),
            TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
        ],
    )

    assert adapter.texts() == ["The failure is the 3DS step."]


async def test_deltas_within_one_text_block_still_join_without_a_break() -> None:
    adapter = FakeChannelAdapter()

    await _render(
        adapter,
        [
            TextDelta(text="forty"),
            TextDelta(text="-two"),
            TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
        ],
    )

    assert adapter.texts() == ["forty-two"]


@pytest.mark.acceptance(spec="channels", scenario="a turn that wrote no text sends no reply")
async def test_a_turn_that_wrote_no_text_sends_no_reply() -> None:
    adapter = FakeChannelAdapter()

    await _render(
        adapter,
        [TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")],
    )

    assert adapter.texts() == []
