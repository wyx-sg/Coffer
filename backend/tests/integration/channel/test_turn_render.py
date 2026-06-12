"""TurnRenderer progress strategy is picked from capabilities, never the type.

supports_edit → one editable progress message, deleted when the turn ends;
without it the renderer sends no tool-progress traffic at all.
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
        pending_approvals={},
        send=send,
    )
    queue: asyncio.Queue[Any] = asyncio.Queue()
    for event in events:
        queue.put_nowait(event)
    queue.put_nowait(None)
    await renderer.consume(queue)


_TOOL_TURN = [
    ToolCall(tool_use_id="t1", tool_name="search", tool_input={"q": "cats"}),
    ToolResult(tool_use_id="t1", tool_name="search", output={"hits": 3}, error=None),
    TextDelta(text="found 3 cats"),
    TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
]


async def test_supports_edit_creates_then_deletes_a_progress_message() -> None:
    adapter = FakeChannelAdapter(supports_edit=True)

    await _render(adapter, _TOOL_TURN)

    # The first send is the progress message created on ToolCall…
    assert adapter.sent[0] == ("owner", "⏳ search")
    progress_id = "m1"  # ids are issued in send order
    # …which is deleted when the turn finishes, before the final reply.
    assert adapter.deleted == [("owner", progress_id)]
    assert adapter.sent[-1] == ("owner", "found 3 cats")


async def test_without_edit_support_no_progress_traffic_is_sent() -> None:
    adapter = FakeChannelAdapter(supports_edit=False)

    await _render(adapter, _TOOL_TURN)

    assert adapter.sent == [("owner", "found 3 cats")]  # the reply, nothing else
    assert adapter.edits == []
    assert adapter.deleted == []
