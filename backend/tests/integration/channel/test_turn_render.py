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

from .conftest import FakeChannelAdapter, wait_until


def _ticking(step: float = 2.0, start: float = 0.0) -> Callable[[], float]:
    """A monotonic clock that advances ``step`` on every call. With ``step`` above
    ``_EDIT_INTERVAL_SECONDS`` (1.5) each consecutive status render passes the edit
    throttle, so streaming edits are deterministic in a test."""
    box = [start]

    def now() -> float:
        value = box[0]
        box[0] += step
        return value

    return now


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


# ---------------------------------------------------------------------------
# FR-037: streaming the reply into one editable status message (supports_edit)
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="009-channels",
    scenario="reply text streams into the editable status message as it arrives",
)
async def test_reply_text_streams_into_the_status_message() -> None:
    adapter = FakeChannelAdapter(supports_edit=True)
    events = [
        ToolCall(tool_use_id="t1", tool_name="search", tool_input={"q": "cats"}),
        TextDelta(text="I found "),
        TextDelta(text="three "),
        TextDelta(text="cats."),
        TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
    ]

    # A ticking clock (step > the 1.5s throttle) makes each render pass the throttle.
    await _render(adapter, events, now=_ticking())

    # Before any text, the status message shows the tool-progress line…
    assert adapter.sent[0] == ("owner", "⏳ search · cats")
    # …then the SAME single message is edited with the growing reply text (plain,
    # not HTML), so the user watches the answer materialize.
    assert ("owner", "m1", "I found") in adapter.edits
    assert adapter.edits[-1] == ("owner", "m1", "I found three cats.")
    # Finish still deletes the status message and sends the final reply once.
    assert adapter.deleted == [("owner", "m1")]
    assert adapter.sent[-1] == ("owner", "I found three cats.")


@pytest.mark.acceptance(
    spec="009-channels",
    scenario="the streamed reply preview is clipped to the platform limit",
)
async def test_streamed_preview_is_clipped_to_the_platform_limit() -> None:
    # A tiny per-message limit forces clipping of the interim preview.
    adapter = FakeChannelAdapter(supports_edit=True, max_message_chars=10)
    body = "0123456789ABCDEFGHIJ"  # 20 chars, twice the limit
    events = [
        # A tool call opens the status message the reply text then streams into.
        ToolCall(tool_use_id="t1", tool_name="search", tool_input={"q": "cats"}),
        TextDelta(text="start"),
        TextDelta(text=body),
        TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
    ]

    await _render(adapter, events, now=_ticking())

    # Every interim text edit fits the platform limit and, when clipped, keeps the
    # TAIL behind a leading ellipsis so the newest text shows.
    assert adapter.edits, "expected at least one interim status edit"
    for _chat, _mid, text in adapter.edits:
        assert len(text) <= 10
    clipped = adapter.edits[-1][2]
    assert clipped == "…BCDEFGHIJ"  # ellipsis + the final 9 chars of the accumulated text
    # The final reply (sent via _finish) is the FULL text, not the clipped preview.
    assert adapter.sent[-1] == ("owner", "start" + body)


@pytest.mark.acceptance(
    spec="009-channels",
    scenario="a slow text-only reply streams into a status message",
)
async def test_slow_text_only_reply_opens_and_streams_a_status_message() -> None:
    # No tool call — a pure explanatory reply. The status message is opened only
    # because the reply runs PAST the throttle interval (the ticking clock, step
    # 2.0 > 1.5s, makes it "slow"), then the growing text streams into it.
    adapter = FakeChannelAdapter(supports_edit=True)
    events = [
        TextDelta(text="First, "),
        TextDelta(text="second, "),
        TextDelta(text="third."),
        TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
    ]

    await _render(adapter, events, now=_ticking())

    # The status message is opened with the streaming reply text (no tool line)…
    assert adapter.sent[0] == ("owner", "First,")
    # …then edited in place as the answer grows…
    assert adapter.edits[-1] == ("owner", "m1", "First, second, third.")
    # …and on finish it is deleted and the final reply is sent once.
    assert adapter.deleted == [("owner", "m1")]
    assert adapter.sent[-1] == ("owner", "First, second, third.")


@pytest.mark.acceptance(
    spec="009-channels",
    scenario="a fast text-only reply opens no status message",
)
async def test_fast_text_only_reply_opens_no_status_message() -> None:
    # A quick reply whose deltas all land within the throttle window (the default
    # constant clock never advances past 0) opens NO placeholder — no
    # create → delete → resend flicker; texts() is exactly the one final reply.
    adapter = FakeChannelAdapter(supports_edit=True)
    events = [
        TextDelta(text="hi "),
        TextDelta(text="there"),
        TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
    ]

    await _render(adapter, events)  # default now=_clock(0.0): elapsed stays 0 < 1.5

    assert adapter.sent == [("owner", "hi there")]
    assert adapter.edits == []
    assert adapter.deleted == []


# ---------------------------------------------------------------------------
# FR-037: typing heartbeat on a supports_typing-only transport (SeaTalk)
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="009-channels",
    scenario="a supports_typing-only DM keeps the typing indicator alive during a long turn",
)
async def test_typing_heartbeat_re_sends_on_a_supports_typing_only_dm() -> None:
    # SeaTalk-shaped: can type, cannot edit; a DM.
    adapter = FakeChannelAdapter(supports_edit=False, supports_typing=True)
    queue: asyncio.Queue[Any] = asyncio.Queue()

    async def send(text: str) -> None:
        await adapter.send_text("owner", text)

    renderer = TurnRenderer(
        channel="st",
        adapter=adapter,
        chat_id="owner",
        conversation_id="c1",
        send=send,
        now=_clock(0.0),
        chat_kind="direct",
        heartbeat_seconds=0.01,  # drive the heartbeat fast
    )
    task = asyncio.create_task(renderer.consume(queue))
    # The turn is "long": events have not arrived yet, so the heartbeat ticks.
    await wait_until(
        lambda: len(adapter.typing) > 1,
        message="expected the typing heartbeat to re-send more than once",
    )
    # Now finish the turn — the heartbeat must be cancelled in the finally.
    queue.put_nowait(TextDelta(text="done"))
    queue.put_nowait(TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"))
    queue.put_nowait(None)
    await task

    assert len(adapter.typing) > 1  # the indicator was re-sent periodically
    assert adapter.sent[-1] == ("owner", "done")  # and the final reply still lands


@pytest.mark.acceptance(
    spec="009-channels",
    scenario="a supports_typing-only group turn posts no interim status message",
)
async def test_no_interim_signal_on_a_supports_typing_only_group_turn() -> None:
    # SeaTalk in a group: no edit, no delete, and single_chat_typing is DM-only —
    # so a group/thread turn gets NO interim signal, only the final chunked reply.
    adapter = FakeChannelAdapter(supports_edit=False, supports_typing=True, supports_groups=True)
    queue: asyncio.Queue[Any] = asyncio.Queue()

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
        heartbeat_seconds=0.01,
    )
    for event in [
        ToolCall(tool_use_id="t1", tool_name="search", tool_input={"q": "cats"}),
        TextDelta(text="found 3 cats"),
        TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
    ]:
        queue.put_nowait(event)
    queue.put_nowait(None)
    await renderer.consume(queue)

    # No heartbeat (group), no editable status message, no edits/deletes — just
    # the single final reply into the originating group/thread.
    assert adapter.typing == []
    assert adapter.edits == []
    assert adapter.deleted == []
    assert adapter.sent == [("gid-1", "found 3 cats")]
