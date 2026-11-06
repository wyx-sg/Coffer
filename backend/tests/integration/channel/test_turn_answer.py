"""Nothing is posted while a turn runs, and the final reply carries only the
answer (spec channels "Send only the answer, once the turn is done")."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from coffer.application.channel.turn_render import TurnRenderer
from coffer.domain.chat.events import TextDelta, ToolCall, ToolResult, TurnDone

from .conftest import FakeChannelAdapter

_DONE = TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")


def _renderer(adapter: FakeChannelAdapter, **kwargs: Any) -> TurnRenderer:
    async def send(text: str) -> None:
        await adapter.send_text("owner", text)

    kwargs.setdefault("now", lambda: 0.0)
    return TurnRenderer(
        channel="st", adapter=adapter, chat_id="owner", conversation_id="c1", send=send, **kwargs
    )


async def _run(renderer: TurnRenderer, events: list[Any]) -> None:
    queue: asyncio.Queue[Any] = asyncio.Queue()
    for event in [*events, None]:
        queue.put_nowait(event)
    await renderer.consume(queue)


@pytest.mark.acceptance(spec="channels", scenario="the final reply carries only the answer")
async def test_the_final_reply_leaves_the_narration_out() -> None:
    adapter = FakeChannelAdapter()

    await _run(
        _renderer(adapter),
        [
            TextDelta(text="Let me check the deploy logs."),
            ToolCall(tool_use_id="t1", tool_name="Bash", tool_input={"command": "tail"}),
            ToolResult(tool_use_id="t1", tool_name="Bash", output="", error=None),
            TextDelta(text="Now the e2e run."),
            ToolCall(tool_use_id="t2", tool_name="Read", tool_input={"file_path": "/a/e2e.log"}),
            TextDelta(text="PR #441 is red on one flaky e2e."),
            _DONE,
        ],
    )

    # Nothing was posted while the turn ran; the reply is one message, the answer alone.
    assert adapter.texts() == ["PR #441 is red on one flaky e2e."]


@pytest.mark.acceptance(
    spec="channels", scenario="a turn that ends on a tool call replies with its last text"
)
async def test_a_turn_ending_on_a_tool_call_replies_with_its_last_text() -> None:
    adapter = FakeChannelAdapter()

    await _run(
        _renderer(adapter),
        [
            TextDelta(text="Checking."),
            ToolCall(tool_use_id="t1", tool_name="Bash", tool_input={"command": "ls"}),
            TextDelta(text="The report is written."),
            ToolCall(tool_use_id="t2", tool_name="Write", tool_input={"file_path": "/a/r.md"}),
            ToolResult(tool_use_id="t2", tool_name="Write", output="", error=None),
            _DONE,
        ],
    )

    assert adapter.texts() == ["The report is written."]
