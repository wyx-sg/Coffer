"""The live surface shows the status block and the answer under it, and the
final reply carries only the answer (spec channels "Show a turn's working state
as one status line")."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from coffer.application.channel.turn_render import TurnRenderer
from coffer.application.channel.turn_status import split_snapshot
from coffer.domain.chat.events import TextDelta, ToolCall, ToolResult, TurnDone

from .conftest import FakeChannelAdapter, wait_until

_DONE = TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")


def _streaming() -> FakeChannelAdapter:
    """A Telegram-shaped transport: a live surface that is scaffolding."""
    return FakeChannelAdapter(supports_edit=True)


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


@pytest.mark.acceptance(
    spec="channels", scenario="narration between tool calls moves to the status line"
)
async def test_narration_moves_up_and_the_answer_grows_under_the_status() -> None:
    adapter = _streaming()

    await _run(
        _renderer(adapter),
        [
            TextDelta(text="Let me check the deploy logs."),
            ToolCall(tool_use_id="t1", tool_name="Bash", tool_input={"description": "tail log"}),
            ToolResult(tool_use_id="t1", tool_name="Bash", output="", error=None),
            TextDelta(text="PR #441 is red on one flaky e2e."),
            _DONE,
        ],
    )

    [live] = adapter.live_handles
    after_tool = [s for s in live.snapshots if "✅ Bash · tail log" in s]
    block, answer = split_snapshot(after_tool[-1])
    assert "💬 Let me check the deploy logs." in block.splitlines()
    assert answer == "PR #441 is red on one flaky e2e."


@pytest.mark.acceptance(spec="channels", scenario="the final reply carries only the answer")
async def test_the_final_reply_leaves_the_narration_out() -> None:
    adapter = _streaming()

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

    [live] = adapter.live_handles
    assert live.closed and live.final == "PR #441 is red on one flaky e2e."
    # The scaffolding was deleted; the reply is one new message, the answer alone.
    assert adapter.deleted
    assert adapter.texts()[-1] == "PR #441 is red on one flaky e2e."
    assert not any("Let me check" in t for t in adapter.texts()[1:])


@pytest.mark.acceptance(
    spec="channels", scenario="a turn that ends on a tool call replies with its last text"
)
async def test_a_turn_ending_on_a_tool_call_replies_with_its_last_text() -> None:
    adapter = FakeChannelAdapter(supports_edit=False, supports_live_text=False)

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


@pytest.mark.acceptance(
    spec="channels", scenario="the status line keeps ticking during a silent tool"
)
async def test_the_header_ticks_while_a_tool_runs_in_silence() -> None:
    adapter = _streaming()
    clock = [0.0]
    renderer = _renderer(adapter, now=lambda: clock[0], tick_seconds=0.01)
    queue: asyncio.Queue[Any] = asyncio.Queue()
    task = asyncio.create_task(renderer.consume(queue))
    queue.put_nowait(ToolCall(tool_use_id="t1", tool_name="Bash", tool_input={"command": "x"}))
    await wait_until(
        lambda: bool(adapter.live_handles) and len(adapter.live_handles[0].snapshots) > 1
    )
    clock[0] = 134.0  # two minutes later, still no event from the tool
    await wait_until(
        lambda: any("2m 14s" in s for s in adapter.live_handles[0].snapshots), timeout=2.0
    )
    queue.put_nowait(_DONE)
    queue.put_nowait(None)
    await task


async def test_hidden_steps_keep_the_step_lines_off_the_surface() -> None:
    adapter = _streaming()

    await _run(
        _renderer(adapter, show_steps=False),
        [ToolCall(tool_use_id="t1", tool_name="Bash", tool_input={"command": "ls"}), _DONE],
    )

    [live] = adapter.live_handles
    assert live.snapshots[-1] == "⏳ Working · 0s · 1 step"
    assert not any("Bash" in s for s in live.snapshots)


async def test_a_long_answer_is_clipped_under_a_header_that_stays() -> None:
    adapter = FakeChannelAdapter(supports_edit=True, max_message_chars=60)
    box = [0.0]

    def ticking() -> float:
        box[0] += 2.0
        return box[0]

    await _run(
        _renderer(adapter, now=ticking),
        [
            ToolCall(tool_use_id="t1", tool_name="Bash", tool_input={"command": "ls"}),
            TextDelta(text="word " * 40),
            _DONE,
        ],
    )

    last = adapter.edits[-1][2]
    assert len(last) <= 60
    assert last.startswith("⏳ Working")
    assert split_snapshot(last)[1].startswith("…")
