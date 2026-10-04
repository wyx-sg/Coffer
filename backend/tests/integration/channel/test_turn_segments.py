"""Text written on either side of a tool call is two paragraphs, not one run-on.

An agent streams "Let me check the logs." — runs a tool — then "The failure is…".
Both arrive as bare ``TextDelta``s, so a renderer that only concatenates them
delivers "…check the logs.The failure is…". The tool call between them is the
boundary, and the final reply keeps both halves with a paragraph break.
"""

from __future__ import annotations

import asyncio
from typing import Any

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


async def test_text_either_side_of_a_tool_call_is_two_paragraphs() -> None:
    adapter = FakeChannelAdapter(supports_edit=False)

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

    assert adapter.texts() == ["Let me check the logs.\n\nThe failure is the 3DS step."]


async def test_deltas_within_one_text_block_still_join_without_a_break() -> None:
    adapter = FakeChannelAdapter(supports_edit=False)

    await _render(
        adapter,
        [
            TextDelta(text="forty"),
            TextDelta(text="-two"),
            TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
        ],
    )

    assert adapter.texts() == ["forty-two"]


async def test_tool_progress_keeps_updating_after_the_agent_has_written_text() -> None:
    # The long-task case: one sentence of narration, then a run of tools. The
    # live surface must keep showing each tool, not freeze on the sentence.
    adapter = FakeChannelAdapter(supports_edit=True)
    box = [0.0]

    def now() -> float:
        box[0] += 2.0
        return box[0]

    async def send(text: str) -> None:
        await adapter.send_text("owner", text)

    renderer = TurnRenderer(
        channel="tg", adapter=adapter, chat_id="owner", conversation_id="c1", send=send, now=now
    )
    queue: asyncio.Queue[Any] = asyncio.Queue()
    for event in [
        TextDelta(text="Let me look at the logs."),
        ToolCall(tool_use_id="t1", tool_name="Bash", tool_input={"description": "tail the log"}),
        ToolCall(tool_use_id="t2", tool_name="Grep", tool_input={"pattern": "3DS"}),
        TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
        None,
    ]:
        queue.put_nowait(event)
    await renderer.consume(queue)

    snapshots = adapter.live_handles[0].snapshots
    assert any("Grep · 3DS" in s for s in snapshots)
