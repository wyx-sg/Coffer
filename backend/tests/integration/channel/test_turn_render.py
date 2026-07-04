"""TurnRenderer progress strategy is picked from capabilities, never the type.

supports_edit → one editable progress message, deleted when the turn ends;
without it the renderer sends no tool-progress traffic at all. Every turn ends
with a compact completion summary (FR-015), capability-agnostic.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest

from coffer.application.channel.turn_render import TurnRenderer
from coffer.domain.chat.events import TextDelta, ToolCall, ToolResult, TurnDone, TurnError

from .conftest import FakeChannelAdapter


def _clock(*values: float) -> Callable[[], float]:
    """A deterministic monotonic clock returning the given values in order
    (last value repeats), so turn duration is fixed in tests."""
    seq = list(values) or [0.0]

    def now() -> float:
        return seq.pop(0) if len(seq) > 1 else seq[0]

    return now


async def _render(
    adapter: FakeChannelAdapter, events: list[Any], *, now: Callable[[], float] | None = None
) -> None:
    async def send(text: str) -> None:
        await adapter.send_text("owner", text)

    renderer = TurnRenderer(
        channel="tg",
        adapter=adapter,
        chat_id="owner",
        conversation_id="c1",
        send=send,
        now=now or _clock(0.0),
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


@pytest.mark.acceptance(
    spec="009-channels",
    scenario="a clean success on an edit-capable channel sends no completion summary",
)
async def test_supports_edit_creates_then_deletes_a_progress_message() -> None:
    adapter = FakeChannelAdapter(supports_edit=True)

    await _render(adapter, _TOOL_TURN)

    # The first send is the progress message created on ToolCall, labelled with
    # a descriptor drawn from the call's input…
    assert adapter.sent[0] == ("owner", "⏳ search · cats")
    progress_id = "m1"  # ids are issued in send order
    # …which is deleted when the turn finishes, before the final reply.
    assert adapter.deleted == [("owner", progress_id)]
    # A clean success on an edit-capable channel ends with the reply itself —
    # no trailing fact summary (the live progress already signalled activity).
    assert adapter.sent[-1] == ("owner", "found 3 cats")
    assert not any(text.startswith("✅ done") for _, text in adapter.sent)


@pytest.mark.acceptance(
    spec="009-channels",
    scenario="a completion summary is sent on a channel that cannot edit messages",
)
async def test_without_edit_support_no_progress_traffic_is_sent() -> None:
    adapter = FakeChannelAdapter(supports_edit=False)

    await _render(adapter, _TOOL_TURN)

    # The reply, then the completion summary — and nothing else (no progress).
    assert adapter.sent == [
        ("owner", "found 3 cats"),
        ("owner", "✅ done · 1 tool · 0.0s"),
    ]
    assert adapter.edits == []
    assert adapter.deleted == []


async def test_summary_reports_duration_and_tokens() -> None:
    adapter = FakeChannelAdapter(supports_edit=False)
    events = [
        TextDelta(text="hi"),
        TurnDone(prompt_tokens=50, completion_tokens=30, stop_reason="end_turn"),
    ]

    await _render(adapter, events, now=_clock(100.0, 101.5))

    assert adapter.sent[-1] == ("owner", "✅ done · 0 tools · 1.5s · 80 tok")


async def test_error_turn_ends_with_a_failed_summary() -> None:
    adapter = FakeChannelAdapter(supports_edit=False)
    events = [TurnError(code="PROVIDER_TIMEOUT", message="upstream timed out")]

    await _render(adapter, events)

    assert adapter.sent[0] == ("owner", "⚠️ upstream timed out [PROVIDER_TIMEOUT]")
    assert adapter.sent[-1] == ("owner", "⚠️ failed · 0 tools · 0.0s")


async def test_interrupted_turn_ends_with_a_stopped_summary() -> None:
    adapter = FakeChannelAdapter(supports_edit=False)
    events = [
        TextDelta(text="partial"),
        TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="interrupted"),
    ]

    await _render(adapter, events)

    assert adapter.sent[-1] == ("owner", "⏹ stopped · 0 tools · 0.0s")


@pytest.mark.acceptance(
    spec="009-channels",
    scenario="channel progress lines describe each tool call from its input",
)
async def test_progress_line_describes_a_bash_call_from_its_input() -> None:
    adapter = FakeChannelAdapter(supports_edit=True)
    events = [
        ToolCall(
            tool_use_id="t1",
            tool_name="Bash",
            tool_input={"command": "ls ~/Desktop", "description": "list the desktop"},
        ),
        TextDelta(text="done"),
        TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
    ]

    await _render(adapter, events)

    # The progress message created on the ToolCall names the tool AND what it does.
    assert adapter.sent[0] == ("owner", "⏳ Bash · list the desktop")


async def test_progress_line_uses_the_file_basename_for_a_read() -> None:
    adapter = FakeChannelAdapter(supports_edit=True)
    events = [
        ToolCall(
            tool_use_id="t1",
            tool_name="Read",
            tool_input={"file_path": "/Users/x/wedding-invitation/data/wedding.json"},
        ),
        TextDelta(text="done"),
        TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
    ]

    await _render(adapter, events)

    assert adapter.sent[0] == ("owner", "⏳ Read · wedding.json")


@pytest.mark.acceptance(
    spec="009-channels",
    scenario="the agent sends a file to the user via a reply marker",
)
async def test_reply_file_marker_uploads_and_is_stripped(tmp_path) -> None:  # type: ignore[no-untyped-def]
    img = tmp_path / "invite.png"
    img.write_bytes(b"PNG-bytes")
    adapter = FakeChannelAdapter(supports_edit=False)
    events = [
        TextDelta(text=f"here you go\n\n![the invitation]({img})"),
        TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
    ]

    await _render(adapter, events)

    # The file was uploaded as a photo with the marker's caption…
    assert adapter.media == [("owner", str(img), "the invitation", True)]
    # …and the marker was removed from the delivered text.
    assert adapter.sent[0] == ("owner", "here you go")


async def test_bare_path_in_prose_is_not_uploaded(tmp_path) -> None:  # type: ignore[no-untyped-def]
    data = tmp_path / "wedding.json"
    data.write_text("{}")
    adapter = FakeChannelAdapter(supports_edit=False)
    events = [
        # A plain mention, not the ![](…) syntax — must not upload.
        TextDelta(text=f"I edited {data} for you."),
        TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
    ]

    await _render(adapter, events)

    assert adapter.media == []
    assert adapter.sent[0] == ("owner", f"I edited {data} for you.")


async def test_marker_for_a_missing_file_is_left_as_text() -> None:
    adapter = FakeChannelAdapter(supports_edit=False)
    events = [
        TextDelta(text="![x](/no/such/file.png)"),
        TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
    ]

    await _render(adapter, events)

    assert adapter.media == []
    assert adapter.sent[0] == ("owner", "![x](/no/such/file.png)")
