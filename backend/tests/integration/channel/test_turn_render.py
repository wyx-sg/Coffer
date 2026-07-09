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
    scenario="a clean success sends no completion summary",
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
    # A clean success ends with the reply itself — no trailing fact summary.
    assert adapter.sent[-1] == ("owner", "found 3 cats")
    assert not any(text.startswith("✅ done") for _, text in adapter.sent)


@pytest.mark.acceptance(
    spec="009-channels",
    scenario="a clean success sends no completion summary",
)
async def test_without_edit_support_no_progress_traffic_is_sent() -> None:
    adapter = FakeChannelAdapter(supports_edit=False)

    await _render(adapter, _TOOL_TURN)

    # Just the reply — no progress traffic AND no completion summary, even on a
    # channel that cannot edit; a clean success needs no fact line anywhere.
    assert adapter.sent == [("owner", "found 3 cats")]
    assert adapter.edits == []
    assert adapter.deleted == []


async def test_summary_reports_duration_and_tokens() -> None:
    # An abnormal ending (here an interrupt) still sends a summary — and it
    # reports tool count, duration, and token usage.
    adapter = FakeChannelAdapter(supports_edit=False)
    events = [
        TextDelta(text="partial"),
        TurnDone(prompt_tokens=50, completion_tokens=30, stop_reason="interrupted"),
    ]

    await _render(adapter, events, now=_clock(100.0, 101.5))

    assert adapter.sent[-1] == ("owner", "⏹ stopped · 0 tools · 1.5s · 80 tok")


@pytest.mark.acceptance(
    spec="009-channels",
    scenario="a turn that does not end normally sends a completion summary",
)
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
async def test_reply_file_sentinel_uploads_and_is_stripped(tmp_path) -> None:  # type: ignore[no-untyped-def]
    img = tmp_path / "invite.png"
    img.write_bytes(b"PNG-bytes")
    adapter = FakeChannelAdapter(supports_edit=False)
    events = [
        # A MEDIA: sentinel line with an optional `| caption`.
        TextDelta(text=f"here you go\n\nMEDIA:{img} | the invitation"),
        TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
    ]

    await _render(adapter, events)

    # The file was uploaded as a photo with the sentinel's caption…
    assert adapter.media == [("owner", str(img), "the invitation", True)]
    # …and the sentinel line was removed from the delivered text.
    assert adapter.sent[0] == ("owner", "here you go")


async def test_reply_file_sentinel_without_caption_uses_filename(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # No `| caption`: the caption defaults to None (adapters fall back to the name).
    img = tmp_path / "invite.png"
    img.write_bytes(b"PNG-bytes")
    adapter = FakeChannelAdapter(supports_edit=False)
    events = [
        TextDelta(text=f"here you go\n\nMEDIA:{img}"),
        TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
    ]

    await _render(adapter, events)

    assert adapter.media == [("owner", str(img), None, True)]
    assert adapter.sent[0] == ("owner", "here you go")


async def test_markdown_image_is_not_uploaded(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # The whole point of the sentinel: a legitimate markdown image the agent wrote
    # to *reference* a real local file must NOT be uploaded — it stays as text.
    img = tmp_path / "diagram.png"
    img.write_bytes(b"PNG")
    adapter = FakeChannelAdapter(supports_edit=False)
    events = [
        TextDelta(text=f"see the diagram ![diagram]({img}) above"),
        TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
    ]

    await _render(adapter, events)

    assert adapter.media == []
    assert adapter.sent[0] == ("owner", f"see the diagram ![diagram]({img}) above")


async def test_bare_path_in_prose_is_not_uploaded(tmp_path) -> None:  # type: ignore[no-untyped-def]
    data = tmp_path / "wedding.json"
    data.write_text("{}")
    adapter = FakeChannelAdapter(supports_edit=False)
    events = [
        # A plain mention, not the MEDIA: sentinel — must not upload.
        TextDelta(text=f"I edited {data} for you."),
        TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
    ]

    await _render(adapter, events)

    assert adapter.media == []
    assert adapter.sent[0] == ("owner", f"I edited {data} for you.")


async def test_sentinel_for_a_missing_file_is_left_as_text() -> None:
    adapter = FakeChannelAdapter(supports_edit=False)
    events = [
        TextDelta(text="MEDIA:/no/such/file.png"),
        TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
    ]

    await _render(adapter, events)

    assert adapter.media == []
    assert adapter.sent[0] == ("owner", "MEDIA:/no/such/file.png")


async def test_sentinel_on_a_non_media_channel_is_replaced_with_a_note(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # A channel with no file support must not leak the raw local path — the
    # sentinel is replaced with a plain note instead of being uploaded or left.
    img = tmp_path / "chart.png"
    img.write_bytes(b"PNG")
    adapter = FakeChannelAdapter(supports_edit=False, supports_media=False)
    events = [
        TextDelta(text=f"here it is\n\nMEDIA:{img} | the chart"),
        TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
    ]

    await _render(adapter, events)

    assert adapter.media == []  # nothing uploaded on a non-media channel
    body = adapter.sent[0][1]
    assert str(img) not in body  # the raw path is not leaked
    assert "the chart" in body and "no file support" in body


async def test_sentinel_path_with_spaces_is_delivered(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # Absolute macOS paths routinely contain spaces — the sentinel must still fire.
    d = tmp_path / "My Files"
    d.mkdir()
    img = d / "chart.png"
    img.write_bytes(b"PNG")
    adapter = FakeChannelAdapter(supports_edit=False)
    events = [
        TextDelta(text=f"MEDIA:{img} | chart"),
        TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
    ]

    await _render(adapter, events)

    assert adapter.media == [("owner", str(img), "chart", True)]


@pytest.mark.acceptance(
    spec="009-channels",
    scenario="SeaTalk outbound media is delivered into the originating thread",
)
async def test_media_returned_in_a_group_thread_is_uploaded_into_that_thread(
    tmp_path,  # type: ignore[no-untyped-def]
) -> None:
    """FR-031: a file the agent returns during a group-thread turn is uploaded
    back into that same chat_kind + thread — send_media is called with the
    renderer's thread_id and chat_kind, so a generated chart lands in the
    originating thread, not the group main chat."""
    img = tmp_path / "chart.png"
    img.write_bytes(b"PNG")
    adapter = FakeChannelAdapter(supports_edit=False, supports_media=True, supports_groups=True)

    async def send(text: str) -> None:
        await adapter.send_text("gid-1", text, thread_id="t1", chat_kind="group")

    renderer = TurnRenderer(
        channel="st",
        adapter=adapter,
        chat_id="gid-1",
        conversation_id="c1",
        send=send,
        now=_clock(0.0),
        thread_id="t1",
        chat_kind="group",
    )
    queue: asyncio.Queue[Any] = asyncio.Queue()
    for event in [
        TextDelta(text=f"MEDIA:{img} | chart"),
        TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
    ]:
        queue.put_nowait(event)
    queue.put_nowait(None)
    await renderer.consume(queue)

    assert adapter.media_routed == [("gid-1", str(img), "chart", True, "t1", "group")]
