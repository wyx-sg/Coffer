"""TurnRenderer progress strategy is picked from capabilities, never the type.

supports_live_text → ONE surface the renderer keeps updating for the whole turn:
Telegram's is a message it edits (deleted when the turn ends, the final reply
sent after it); SeaTalk's is a stream that finishes as the reply itself. A
transport with neither sends no interim traffic at all. Every turn that ends
abnormally closes with a compact completion summary (FR-015),
capability-agnostic.
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
    ``_UPDATE_INTERVAL_SECONDS`` (1.5) each consecutive status render passes the
    throttle, so live updates are deterministic in a test."""
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
    spec="channels",
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
    spec="channels",
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
    spec="channels",
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
    spec="channels",
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
    spec="channels",
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
    spec="channels",
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
    spec="channels",
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
    spec="channels",
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
    spec="channels",
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
    spec="channels",
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
    spec="channels",
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
    assert adapter.typing_routed[0] == ("owner", "direct", "")  # DM endpoint, no thread
    assert adapter.sent[-1] == ("owner", "done")  # and the final reply still lands


async def test_typing_heartbeat_re_sends_in_a_group_thread_when_group_typing_is_supported() -> None:
    """A group turn beats too on a transport that holds the group typing
    endpoint (SeaTalk's ``group_chat_typing``): with no reactions to ack with,
    this is the ONLY acknowledgement between the @mention and the first live
    update, and it must land in the thread the turn came from."""
    adapter = FakeChannelAdapter(
        supports_edit=False,
        supports_live_text=False,
        supports_typing=True,
        supports_groups=True,
    )
    queue: asyncio.Queue[Any] = asyncio.Queue()

    async def send(text: str) -> None:
        await adapter.send_text("gid-1", text, thread_id="th-1", chat_kind="group")

    renderer = TurnRenderer(
        channel="st",
        adapter=adapter,
        chat_id="gid-1",
        conversation_id="c1",
        send=send,
        now=_clock(0.0),
        thread_id="th-1",
        chat_kind="group",
        heartbeat_seconds=0.01,
    )
    task = asyncio.create_task(renderer.consume(queue))
    await wait_until(
        lambda: len(adapter.typing) > 1,
        message="expected the group typing heartbeat to re-send more than once",
    )
    queue.put_nowait(TextDelta(text="done"))
    queue.put_nowait(TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"))
    queue.put_nowait(None)
    await task

    # Routed at the group endpoint, in the originating thread — a DM-shaped
    # ping here would just be a failed call the suppression swallows.
    assert set(adapter.typing_routed) == {("gid-1", "group", "th-1")}


async def test_no_typing_heartbeat_on_a_transport_that_reacts() -> None:
    """FR-036: a transport with reactions (Telegram) already acked the user's
    message with 👀 — the heartbeat is gated on the RECEIPT mechanism, so it
    stays off there even in a group where group typing is available."""
    adapter = FakeChannelAdapter(
        supports_typing=True,
        supports_reactions=True,
        supports_groups=True,
    )
    queue: asyncio.Queue[Any] = asyncio.Queue()

    async def send(text: str) -> None:
        await adapter.send_text("gid-1", text, thread_id="th-1", chat_kind="group")

    renderer = TurnRenderer(
        channel="tg",
        adapter=adapter,
        chat_id="gid-1",
        conversation_id="c1",
        send=send,
        now=_clock(0.0),
        thread_id="th-1",
        chat_kind="group",
        heartbeat_seconds=0.001,
    )
    for event in [
        TextDelta(text="done"),
        TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
    ]:
        queue.put_nowait(event)
    queue.put_nowait(None)
    await renderer.consume(queue)

    assert adapter.typing == []


@pytest.mark.acceptance(
    spec="channels",
    scenario="a transport with no live-text surface posts no interim status message",
)
async def test_no_interim_signal_without_a_live_text_surface_in_a_group() -> None:
    # A transport that can neither edit nor stream, in a group whose typing
    # endpoint it does not hold either: NO interim signal at all, only the
    # final chunked reply. (SeaTalk left this shape behind — it streams now.)
    adapter = FakeChannelAdapter(
        supports_edit=False,
        supports_live_text=False,
        supports_typing=True,
        supports_groups=True,
    )
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

    # No heartbeat (group), no live surface, no edits/deletes — just the single
    # final reply into the originating group/thread.
    assert adapter.typing == []
    assert adapter.edits == []
    assert adapter.deleted == []
    assert adapter.sent == [("gid-1", "found 3 cats")]


# ---------------------------------------------------------------------------
# FR-037: a transport that cannot edit but CAN stream (SeaTalk)
# ---------------------------------------------------------------------------


def _streaming_adapter(**kwargs: Any) -> FakeChannelAdapter:
    """SeaTalk-shaped: no edit, no delete — but one message that grows in place
    and, once finished, IS the reply."""
    kwargs.setdefault("live_text_persists", True)
    adapter = FakeChannelAdapter(supports_edit=False, supports_live_text=True, **kwargs)
    adapter.live_text_finalizes = True
    return adapter


@pytest.mark.acceptance(
    spec="channels",
    scenario="a reply grows in place on a transport that streams but cannot edit",
)
async def test_streaming_transport_grows_one_message_instead_of_sending_fragments() -> None:
    adapter = _streaming_adapter(supports_groups=True)

    async def send(text: str) -> None:
        await adapter.send_text("gid-1", text, thread_id="t1", chat_kind="group")

    renderer = TurnRenderer(
        channel="st",
        adapter=adapter,
        chat_id="gid-1",
        conversation_id="c1",
        send=send,
        now=_ticking(),
        thread_id="t1",
        chat_kind="group",
    )
    queue: asyncio.Queue[Any] = asyncio.Queue()
    for event in [
        ToolCall(tool_use_id="t1", tool_name="search", tool_input={"q": "cats"}),
        TextDelta(text="I found "),
        TextDelta(text="three "),
        TextDelta(text="cats."),
        TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
    ]:
        queue.put_nowait(event)
    queue.put_nowait(None)
    await renderer.consume(queue)

    [live] = adapter.live_handles
    # The tool line opens the surface, then every later snapshot carries the FULL
    # accumulated reply — the platform re-renders the latest text, never a delta.
    # The surface opens the moment the turn starts, with the acknowledgement —
    # the reply grows out of that same message.
    assert live.snapshots[0] == "⏳ Got it — working on this…"
    assert live.snapshots[1] == "⏳ search · cats"
    assert live.snapshots[2:] == ["I found", "I found three", "I found three cats."]
    assert live.closed and live.final == "I found three cats."
    # Exactly ONE message reached the chat (the stream's own), routed into the
    # originating group thread — no fragments, and no duplicate final send.
    # The ONE message the turn ever posts is the stream's opening one — the
    # acknowledgement — which every later snapshot rewrites in place.
    assert adapter.sent == [("gid-1", "⏳ Got it — working on this…")]
    assert adapter.sent_routed == [("gid-1", "⏳ Got it — working on this…", "t1", "group")]
    assert adapter.edits == [] and adapter.deleted == []  # it can do neither


async def test_streaming_transport_delivers_an_interrupted_reply_in_place() -> None:
    # The stream is the message: an abnormal ending still closes it with the
    # final body, and only the fact summary follows as its own message.
    adapter = _streaming_adapter()

    await _render(
        adapter,
        [
            TextDelta(text="partial"),
            TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="interrupted"),
        ],
        now=_ticking(),
    )

    [live] = adapter.live_handles
    assert live.final == "partial\n\n⏹ Stopped."
    texts = adapter.texts()
    assert texts[0] == "⏳ Got it — working on this…"  # opened at once, then grown
    assert texts[1].startswith("⏹ stopped · 0 tools ·")  # the summary follows it


async def test_a_transport_that_refuses_a_live_surface_is_asked_once_and_degrades() -> None:
    # open_live_text may answer None (nothing available right now). The turn then
    # behaves exactly as a transport without the capability: no interim traffic,
    # one final reply — and the transport is not re-asked on every event.
    adapter = FakeChannelAdapter(supports_edit=False, supports_live_text=True)
    adapter.live_text_unavailable = True

    await _render(adapter, _TOOL_TURN, now=_ticking())

    assert adapter.live_handles == []
    assert adapter.sent == [("owner", "found 3 cats")]
    assert adapter.edits == [] and adapter.deleted == []


async def test_a_persisting_surface_acknowledges_before_the_turn_produces_anything() -> None:
    """The wait between a message and an answer is all the user sees otherwise,
    and on a long turn it reads as the bot having missed them. Where the surface
    BECOMES the reply, opening it at once costs nothing: the acknowledgement is
    the same message the answer grows out of, never a second one."""
    adapter = _streaming_adapter()

    await _render(adapter, [TextDelta(text="the answer")], now=_ticking())

    [live] = adapter.live_handles
    assert live.snapshots[0] == "⏳ Got it — working on this…"
    assert live.final == "the answer"  # replaced in place by the reply
    # The stream's opening message is the ONLY message: the reply is that same
    # one, grown — never an acknowledgement followed by a second answer.
    assert adapter.texts() == ["⏳ Got it — working on this…"]


async def test_a_scaffolding_surface_is_not_opened_before_there_is_something_to_show() -> None:
    """Telegram's live surface is a status message the renderer DELETES before
    sending the real reply. Opening it to acknowledge would post something only
    to take it away again, so no acknowledgement is offered there — its 👀
    receipt reaction already says the message was heard."""
    adapter = FakeChannelAdapter(supports_edit=True)  # live_text_persists stays False

    # A clock that never advances: the reply lands well inside the window below
    # which a scaffolding surface is not worth opening.
    await _render(adapter, [TextDelta(text="quick")])

    assert adapter.live_handles == []  # nothing opened for a reply this fast
    assert adapter.sent == [("owner", "quick")]


async def test_an_upload_says_what_it_is_uploading(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # Claiming to type while a file goes up is the wrong busy signal.
    img = tmp_path / "chart.png"
    img.write_bytes(b"PNG-bytes")
    doc = tmp_path / "report.pdf"
    doc.write_bytes(b"%PDF-1.4")
    adapter = FakeChannelAdapter(supports_edit=False)

    await _render(
        adapter,
        [
            TextDelta(text=f"MEDIA:{img}\n\nMEDIA:{doc}"),
            TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
        ],
    )

    assert "upload_photo" in adapter.typing_actions
    assert "upload_document" in adapter.typing_actions


def test_the_typing_heartbeat_outpaces_the_indicator_it_refreshes() -> None:
    """SeaTalk shows the cue for four seconds. A heartbeat slower than that
    leaves it dark between beats, and a cue that blinks reads as something
    going wrong rather than as something working."""
    from coffer.application.channel.turn_render import _TYPING_HEARTBEAT_SECONDS

    assert _TYPING_HEARTBEAT_SECONDS < 4.0


# ---------------------------------------------------------------------------
# FR-070: a group reply opens by @mentioning whoever asked
# ---------------------------------------------------------------------------

#: The fake's mention spelling, shaped like SeaTalk's real one so a test reads
#: the way the wire does. The transport's own template lives in the adapter
#: (``seatalk_send.SEATALK_MENTION_TEMPLATE``) and is asserted against the real
#: wire body in the SeaTalk adapter tests.
_MENTION = '<mention-tag target="seatalk://user?id={user_id}"/>'
#: Its documented sibling, keyed on the member's address — the fallback for a
#: sender whose id is missing. The placeholder is the same so one literal
#: replace serves both.
_MENTION_BY_EMAIL = '<mention-tag target="seatalk://user?email={user_id}"/>'


async def _group_reply(
    adapter: FakeChannelAdapter,
    *,
    mention_user_id: str,
    mention_user_email: str = "",
    chat_kind: str = "group",
    events: list[Any] | None = None,
) -> None:
    async def send(text: str) -> None:
        await adapter.send_text("gid-1", text, thread_id="t1", chat_kind=chat_kind)

    renderer = TurnRenderer(
        channel="st",
        adapter=adapter,
        chat_id="gid-1",
        conversation_id="c1",
        send=send,
        now=_ticking(),
        thread_id="t1",
        chat_kind=chat_kind,
        mention_user_id=mention_user_id,
        mention_user_email=mention_user_email,
    )
    queue: asyncio.Queue[Any] = asyncio.Queue()
    for event in events or [
        TextDelta(text="the answer"),
        TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
    ]:
        queue.put_nowait(event)
    queue.put_nowait(None)
    await renderer.consume(queue)


@pytest.mark.acceptance(
    spec="channels",
    scenario="a group reply @mentions whoever asked",
)
async def test_a_group_reply_opens_with_a_mention_of_the_asker() -> None:
    # No live surface here (supports_live_text off): the ordinary group send is
    # the whole reply, and it is the other place a mention may appear.
    adapter = FakeChannelAdapter(
        supports_edit=False,
        supports_live_text=False,
        supports_groups=True,
        mention_template=_MENTION,
    )

    await _group_reply(adapter, mention_user_id="st-77")

    assert adapter.texts() == ['<mention-tag target="seatalk://user?id=st-77"/> the answer']


@pytest.mark.acceptance(
    spec="channels",
    scenario="a direct reply carries no mention",
)
async def test_a_dm_reply_never_mentions_the_sender() -> None:
    """A 1:1 chat has nobody to disambiguate — an @ there is only shouting."""
    adapter = FakeChannelAdapter(
        supports_edit=False,
        supports_live_text=False,
        mention_template=_MENTION,
    )

    await _group_reply(adapter, mention_user_id="st-77", chat_kind="direct")

    assert adapter.texts() == ["the answer"]


async def test_a_sender_with_no_mention_id_gets_a_clean_reply() -> None:
    """A bot or system-account sender carries no id to point a mention at, and a
    transport that cannot mention declares no template. Either way the reply is
    the reply — never a half-built tag, never a failure."""
    mentionable = FakeChannelAdapter(
        supports_edit=False,
        supports_live_text=False,
        supports_groups=True,
        mention_template=_MENTION,
    )
    await _group_reply(mentionable, mention_user_id="")
    assert mentionable.texts() == ["the answer"]

    # And the mirror case: an id, but a transport with no mention spelling.
    speechless = FakeChannelAdapter(
        supports_edit=False, supports_live_text=False, supports_groups=True
    )
    await _group_reply(speechless, mention_user_id="st-77")
    assert speechless.texts() == ["the answer"]


@pytest.mark.acceptance(
    spec="channels",
    scenario="a streamed group reply is created already mentioning the asker",
)
async def test_the_mention_is_in_the_message_the_stream_is_created_as() -> None:
    """A platform decides @ notifications when the message is CREATED. The
    mention used to go on the finished snapshot alone, which RENDERED as a name
    (the tag is in the content the client shows) while notifying nobody —
    observed live. So the very first snapshot, the one that posts the message,
    carries it; and every snapshot after it does too, or the mention would appear
    at creation, vanish for the whole stream, and come back at the end."""
    adapter = _streaming_adapter(supports_groups=True, mention_template=_MENTION)

    await _group_reply(
        adapter,
        mention_user_id="st-77",
        events=[
            TextDelta(text="I found "),
            TextDelta(text="three "),
            TextDelta(text="cats."),
            TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
        ],
    )

    tag = '<mention-tag target="seatalk://user?id=st-77"/>'
    [live] = adapter.live_handles
    # The snapshot that CREATES the message — the acknowledgement — is mentioned.
    assert live.snapshots[0] == f"{tag} ⏳ Got it — working on this…"
    # …as is every interim one after it, and the body that closes the stream.
    assert live.snapshots and all(s.startswith(tag) for s in live.snapshots)
    assert live.final == f"{tag} I found three cats."
    # Exactly once each: no path prefixes a snapshot that is already prefixed.
    assert all(s.count("mention-tag") == 1 for s in [*live.snapshots, live.final])
    # The stream IS the reply, so nothing is sent a second time.
    assert adapter.texts() == [f"{tag} ⏳ Got it — working on this…"]


async def test_no_path_mentions_twice_when_tool_progress_opens_the_surface() -> None:
    """``_open_live`` is reached from the acknowledgement AND lazily from the
    status renderer. Both hand it raw text, and the mention is applied in one
    place — the one way to get two tags in a snapshot is for a caller to prefix
    before handing over. This drives the lazy path (no acknowledgement, because
    the surface does not persist) through tool lines and then reply text."""
    adapter = _streaming_adapter(
        supports_groups=True, mention_template=_MENTION, live_text_persists=False
    )

    await _group_reply(
        adapter,
        mention_user_id="st-77",
        events=[
            ToolCall(tool_use_id="t1", tool_name="Bash", tool_input={"command": "ls"}),
            ToolResult(tool_use_id="t1", tool_name="Bash", output={"out": "a b"}, error=None),
            TextDelta(text="done looking."),
            TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
        ],
    )

    [live] = adapter.live_handles
    assert live.snapshots  # the lazy open really happened
    assert all(s.count("mention-tag") == 1 for s in [*live.snapshots, live.final])


@pytest.mark.acceptance(
    spec="channels",
    scenario="a sender with no id is mentioned by address instead",
)
async def test_a_sender_with_no_id_is_mentioned_by_email_where_the_platform_allows() -> None:
    """The platform documents two mention targets. The id is primary — it is the
    one always present on the inbound event — and the address is the fallback for
    the case the id is missing, not a second mention."""
    adapter = FakeChannelAdapter(
        supports_edit=False,
        supports_live_text=False,
        supports_groups=True,
        mention_template=_MENTION,
        mention_email_template=_MENTION_BY_EMAIL,
    )

    await _group_reply(adapter, mention_user_id="", mention_user_email="ada_l@example.com")

    assert adapter.texts() == [
        '<mention-tag target="seatalk://user?email=ada_l@example.com"/> the answer'
    ]


async def test_the_id_wins_when_both_an_id_and_an_address_are_known() -> None:
    adapter = FakeChannelAdapter(
        supports_edit=False,
        supports_live_text=False,
        supports_groups=True,
        mention_template=_MENTION,
        mention_email_template=_MENTION_BY_EMAIL,
    )

    await _group_reply(adapter, mention_user_id="st-77", mention_user_email="ada_l@example.com")

    assert adapter.texts() == ['<mention-tag target="seatalk://user?id=st-77"/> the answer']


def test_a_mention_is_never_built_from_an_id_that_is_not_one() -> None:
    """An id that could break the markup it goes inside is dropped rather than
    interpolated: the reader would see raw tag source, and Coffer would have put
    attacker-shaped text inside its own markup."""
    from coffer.application.channel.turn_text import mention_prefix

    assert mention_prefix(_MENTION, "st-77") == '<mention-tag target="seatalk://user?id=st-77"/>'
    assert mention_prefix(_MENTION, '"/><b>x') == ""
    assert mention_prefix(_MENTION, "") == ""
    assert mention_prefix("", "st-77") == ""


def test_an_address_is_held_to_the_same_bar_as_an_id() -> None:
    """The fallback is a second way to be interpolated into Coffer's own markup,
    so it is gated the same way: one ``@``, a dotted domain, and nothing that
    could break out of the attribute."""
    from coffer.application.channel.turn_text import mention_prefix

    def by_email(value: str) -> str:
        return mention_prefix("", "", email_template=_MENTION_BY_EMAIL, user_email=value)

    assert by_email("ada_l@example.com") == (
        '<mention-tag target="seatalk://user?email=ada_l@example.com"/>'
    )
    assert by_email('x"/><b>y@example.com') == ""
    assert by_email("not-an-address") == ""
    assert by_email("two@at@example.com") == ""
    assert by_email("") == ""
