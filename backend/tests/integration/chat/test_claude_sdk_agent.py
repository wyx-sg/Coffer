"""SDK-backed Claude adapter tests (spec channels).

Drives ``ClaudeSdkAgentAdapter`` through a ``FakeSdkSession`` that replays a
scripted list of SDK message objects. No real ``claude`` binary or network is
touched — everything goes through the fake. Agents always run with full
permissions (``permission_mode="bypassPermissions"``), so there is no per-tool
approval relay.
"""

from __future__ import annotations

import asyncio
import base64
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    UserMessage,
)
from claude_agent_sdk import (
    TextBlock as SdkTextBlock,
)
from claude_agent_sdk import (
    ToolResultBlock as SdkToolResultBlock,
)
from claude_agent_sdk import (
    ToolUseBlock as SdkToolUseBlock,
)

from coffer.domain.chat.attachment import Attachment
from coffer.domain.chat.events import (
    TextDelta,
    ToolCall,
    ToolResult,
    TurnDone,
    TurnError,
    TurnStarted,
)
from coffer.domain.chat.message import Message, Role, TextBlock
from coffer.infrastructure.chat.claude_sdk_agent import (
    ClaudeParseState,
    ClaudeSdkAgentAdapter,
    map_sdk_message,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeSdkSession:
    """A ``ClaudeSdkSession`` that replays canned messages."""

    def __init__(
        self,
        options: ClaudeAgentOptions,
        messages: list[Any],
        block_after: int | None = None,
    ) -> None:
        self.options = options
        self._messages = messages
        # If set, the stream pauses on this event so a cancel can be injected.
        self._block_after = block_after
        self.connected_prompt: str | list[dict[str, Any]] | None = None
        self.interrupted = False
        self.disconnected = False

    async def connect(self, prompt: str | list[dict[str, Any]]) -> None:
        self.connected_prompt = prompt

    async def receive_messages(self) -> AsyncIterator[Any]:
        for idx, msg in enumerate(self._messages):
            yield msg
            if self._block_after is not None and idx == self._block_after:
                # Hang so the consuming turn can be cancelled at a known point.
                await asyncio.sleep(3600)

    async def interrupt(self) -> None:
        self.interrupted = True

    async def disconnect(self) -> None:
        self.disconnected = True


@dataclass
class _Factory:
    """A scripted ``SdkSessionFactory`` capturing the options it was built with."""

    messages: list[Any]
    block_after: int | None = None
    last_options: ClaudeAgentOptions | None = field(default=None, init=False)
    session: FakeSdkSession | None = field(default=None, init=False)

    def __call__(self, options: ClaudeAgentOptions) -> FakeSdkSession:
        self.last_options = options
        self.session = FakeSdkSession(options, self.messages, self.block_after)
        return self.session


def _user_turn(text: str) -> list[Message]:
    return [
        Message(
            id=uuid.uuid4().hex,
            conversation_id="c1",
            seq=0,
            role=Role.USER,
            content=[TextBlock(text=text)],
            status="complete",
            model_id=None,
            prompt_tokens=None,
            completion_tokens=None,
            created_at=datetime.now(tz=UTC),
        )
    ]


async def _dummy_sink(sid: str) -> None:
    return None


class _FakeExtractor:
    """A ``DocumentExtractor`` that returns canned text (no ``markitdown``)."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[str] = []

    async def extract(self, path: str) -> str:
        self.calls.append(path)
        return self.text


def _adapter(
    factory: _Factory,
    *,
    on_session: Any = _dummy_sink,
    resume: str | None = None,
    extra: dict[str, Any] | None = None,
    document_extractor: Any = None,
) -> ClaudeSdkAgentAdapter:
    return ClaudeSdkAgentAdapter(
        cwd="/tmp",
        resume_session=resume,
        extra=extra or {},
        session_factory=factory,
        on_session=on_session,
        document_extractor=document_extractor,
    )


async def _collect(
    adapter: ClaudeSdkAgentAdapter,
    history: list[Message],
    attachments: Any = (),
):
    stream = await adapter.run_turn(history=history, attachments=attachments)
    return [ev async for ev in stream]


# ---------------------------------------------------------------------------
# Attachment materialisation (spec channels channel media)
# ---------------------------------------------------------------------------


def test_build_content_is_the_plain_prompt_without_attachments() -> None:
    # No attachments → unchanged behaviour: the content is the bare string.
    assert ClaudeSdkAgentAdapter._build_content("hello", []) == "hello"


@pytest.mark.acceptance(
    spec="channels",
    scenario="an inbound image reaches a vision agent as an inline block",
)
def test_build_content_inlines_an_image_as_a_base64_block(tmp_path: Any) -> None:
    img = tmp_path / "photo.png"
    img.write_bytes(b"\x89PNG-fake")
    att = Attachment(path=str(img), mime="image/png", filename="photo.png")

    content = ClaudeSdkAgentAdapter._build_content("what is this?", [att])

    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "what is this?"}
    image = content[1]
    assert image["type"] == "image"
    assert image["source"]["type"] == "base64"
    assert image["source"]["media_type"] == "image/png"
    # The bytes are read from disk and encoded here, never stored as base64.
    assert base64.b64decode(image["source"]["data"]) == b"\x89PNG-fake"


def test_build_content_hands_off_a_non_vision_file_by_path(tmp_path: Any) -> None:
    data = tmp_path / "notes.csv"
    data.write_text("a,b\n1,2\n")
    att = Attachment(path=str(data), mime="text/csv", filename="notes.csv")

    content = ClaudeSdkAgentAdapter._build_content("", [att])

    # A non-vision file is not inlined — the agent gets its path to open.
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert str(data) in content[0]["text"]


def test_build_content_does_not_inline_an_unsupported_image_format(tmp_path: Any) -> None:
    # An image/heic (e.g. an iPhone photo sent as a document) is NOT an API-inlinable
    # type — inlining it would 400 the turn, so it falls to the path pointer instead.
    heic = tmp_path / "photo.heic"
    heic.write_bytes(b"HEIC-bytes")
    att = Attachment(path=str(heic), mime="image/heic", filename="photo.heic")

    content = ClaudeSdkAgentAdapter._build_content("", [att])

    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert str(heic) in content[0]["text"]


def test_build_content_no_longer_inlines_a_pdf_as_a_document_block(tmp_path: Any) -> None:
    # FR-030: documents are text-extracted upstream, so a PDF that reaches
    # _build_content (extraction absent/failed) degrades to a path note — not a
    # base64 ``document`` block (uniform text-or-path across all agents).
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.7 fake")
    att = Attachment(path=str(pdf), mime="application/pdf", filename="report.pdf")

    content = ClaudeSdkAgentAdapter._build_content("", [att])

    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert str(pdf) in content[0]["text"]
    assert not any(b.get("type") == "document" for b in content)


@pytest.mark.asyncio
async def test_pdf_reaches_claude_as_extracted_text_not_a_document_block(tmp_path: Any) -> None:
    # FR-030: a PDF is text-extracted and folded into the prompt as a labelled
    # text block; it is NOT sent as a base64 ``document`` block. An image on the
    # same turn stays vision-inlined — only documents go through extraction.
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.7 fake")
    img = tmp_path / "chart.png"
    img.write_bytes(b"\x89PNG-fake")
    pdf_att = Attachment(path=str(pdf), mime="application/pdf", filename="report.pdf")
    img_att = Attachment(path=str(img), mime="image/png", filename="chart.png")
    extractor = _FakeExtractor("Quarterly revenue was $4.2M.")

    factory = _Factory(_basic_messages())
    adapter = _adapter(factory, document_extractor=extractor)
    events = await _collect(adapter, _user_turn("summarise this"), attachments=(pdf_att, img_att))

    assert isinstance(events[-1], TurnDone)
    assert extractor.calls == [str(pdf)]
    assert factory.session is not None
    content = factory.session.connected_prompt
    assert isinstance(content, list)
    # The extracted PDF text is a labelled text block…
    text_blocks = [b["text"] for b in content if b.get("type") == "text"]
    joined = "\n".join(text_blocks)
    assert "[Document: report.pdf]" in joined
    assert "Quarterly revenue was $4.2M." in joined
    # …no document/binary block was sent for the PDF…
    assert not any(b.get("type") == "document" for b in content)
    # …and the image stays vision-inlined (images are untouched by FR-030).
    assert any(b.get("type") == "image" for b in content)


# Canned SDK message stream: init → assistant text+tool → tool result → text → done.
def _basic_messages() -> list[Any]:
    return [
        SystemMessage(subtype="init", data={"session_id": "sess-1"}),
        AssistantMessage(
            content=[
                SdkTextBlock(text="Let me check."),
                SdkToolUseBlock(id="tu_1", name="Bash", input={"command": "ls"}),
            ],
            model="claude",
        ),
        UserMessage(
            content=[SdkToolResultBlock(tool_use_id="tu_1", content="file.txt", is_error=False)]
        ),
        AssistantMessage(content=[SdkTextBlock(text="There is one file.")], model="claude"),
        ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id="sess-1",
            usage={"input_tokens": 12, "output_tokens": 7},
            total_cost_usd=0.0,
        ),
    ]


# ---------------------------------------------------------------------------
# map_sdk_message — pure mapping
# ---------------------------------------------------------------------------


def test_map_sdk_message_full_sequence_has_one_terminal():
    # No StreamEvents in this stream (case c: an older CLI that does not support
    # partial messages, or a turn with no text increments) — each finished text
    # block is emitted whole, exactly as before partial messages were enabled.
    state = ClaudeParseState()
    events = []
    for msg in _basic_messages():
        events.extend(map_sdk_message(msg, state))

    assert state.session_id == "sess-1"
    deltas = [e.text for e in events if isinstance(e, TextDelta)]
    assert deltas == ["Let me check.", "There is one file."]
    calls = [e for e in events if isinstance(e, ToolCall)]
    assert len(calls) == 1
    assert calls[0].tool_use_id == "tu_1"
    assert calls[0].tool_name == "Bash"
    assert calls[0].tool_input == {"command": "ls"}
    results = [e for e in events if isinstance(e, ToolResult)]
    assert len(results) == 1
    assert results[0].tool_name == "Bash"  # resolved from state.tool_names
    assert results[0].error is None
    terminals = [e for e in events if isinstance(e, (TurnDone, TurnError))]
    assert len(terminals) == 1
    done = terminals[0]
    assert isinstance(done, TurnDone)
    assert (done.prompt_tokens, done.completion_tokens) == (12, 7)
    assert state.terminal_emitted is True


def test_map_sdk_message_error_result_is_turn_error():
    state = ClaudeParseState()
    msg = ResultMessage(
        subtype="error_during_execution",
        duration_ms=1,
        duration_api_ms=1,
        is_error=True,
        num_turns=1,
        session_id="s",
        usage=None,
        total_cost_usd=0.0,
        result="boom",
    )
    events = map_sdk_message(msg, state)
    assert len(events) == 1
    assert isinstance(events[0], TurnError)
    assert "boom" in events[0].message


def test_map_sdk_message_tool_result_error_maps_to_error_field():
    state = ClaudeParseState()
    state.tool_names["tu_9"] = "Bash"
    msg = UserMessage(
        content=[SdkToolResultBlock(tool_use_id="tu_9", content="bad", is_error=True)]
    )
    events = map_sdk_message(msg, state)
    assert len(events) == 1
    result = events[0]
    assert isinstance(result, ToolResult)
    assert result.output is None
    assert result.error == "bad"


# ---------------------------------------------------------------------------
# Partial messages — incremental text without doubling the reply
# ---------------------------------------------------------------------------


def _text_delta(text: str, *, index: int = 0, parent: str | None = None) -> StreamEvent:
    """A raw ``content_block_delta`` carrying one text increment."""
    return StreamEvent(
        uuid="evt",
        session_id="sess-1",
        event={
            "type": "content_block_delta",
            "index": index,
            "delta": {"type": "text_delta", "text": text},
        },
        parent_tool_use_id=parent,
    )


def _raw(event: dict[str, Any]) -> StreamEvent:
    return StreamEvent(uuid="evt", session_id="sess-1", event=event)


def _map_all(messages: list[Any], state: ClaudeParseState | None = None) -> list[Any]:
    state = state or ClaudeParseState()
    out: list[Any] = []
    for msg in messages:
        out.extend(map_sdk_message(msg, state))
    return out


def _joined(events: list[Any]) -> str:
    """What a consumer builds — both turn_render and turn_runner concatenate."""
    return "".join(e.text for e in events if isinstance(e, TextDelta))


def test_stream_deltas_arrive_one_by_one_and_the_final_block_adds_nothing():
    # (a) The deltas cover the finished block exactly: the block itself must emit
    # nothing, or every reply would be sent twice.
    events = _map_all(
        [
            _text_delta("Hello"),
            _text_delta(", "),
            _text_delta("world."),
            AssistantMessage(content=[SdkTextBlock(text="Hello, world.")], model="claude"),
        ]
    )

    assert [e.text for e in events if isinstance(e, TextDelta)] == ["Hello", ", ", "world."]
    assert _joined(events) == "Hello, world."


def test_a_late_stream_delta_is_recovered_from_the_final_block():
    # (b) The deltas are a strict prefix of the finished block (a dropped or late
    # event): only the missing remainder is emitted.
    events = _map_all(
        [
            _text_delta("Hello, "),
            AssistantMessage(content=[SdkTextBlock(text="Hello, world.")], model="claude"),
        ]
    )

    assert [e.text for e in events if isinstance(e, TextDelta)] == ["Hello, ", "world."]
    assert _joined(events) == "Hello, world."


def test_a_final_block_disagreeing_with_the_stream_is_not_sent_again():
    # Defensive: if the finished block is not an extension of what streamed, the
    # reader has already seen the streamed text — emitting the block on top of it
    # would duplicate the reply.
    events = _map_all(
        [
            _text_delta("Hello, world."),
            AssistantMessage(content=[SdkTextBlock(text="Something else")], model="claude"),
        ]
    )

    assert _joined(events) == "Hello, world."


def test_the_accumulator_resets_between_assistant_messages():
    # (d) A turn with tool use between two assistant messages: message 2 must be
    # measured against its own deltas, not message 1's text.
    events = _map_all(
        [
            _text_delta("Let me "),
            _text_delta("check."),
            AssistantMessage(
                content=[
                    SdkTextBlock(text="Let me check."),
                    SdkToolUseBlock(id="tu_1", name="Bash", input={"command": "ls"}),
                ],
                model="claude",
            ),
            UserMessage(
                content=[SdkToolResultBlock(tool_use_id="tu_1", content="file.txt", is_error=False)]
            ),
            _text_delta("There is "),
            _text_delta("one file."),
            AssistantMessage(content=[SdkTextBlock(text="There is one file.")], model="claude"),
        ]
    )

    assert _joined(events) == "Let me check.There is one file."
    calls = [e for e in events if isinstance(e, ToolCall)]
    assert len(calls) == 1
    assert (calls[0].tool_use_id, calls[0].tool_name) == ("tu_1", "Bash")
    assert calls[0].tool_input == {"command": "ls"}
    results = [e for e in events if isinstance(e, ToolResult)]
    assert len(results) == 1
    assert results[0].tool_name == "Bash"


def test_each_text_block_is_matched_against_its_own_streamed_run():
    # One message may hold text, a tool call, then more text. Each run of stream
    # events opens its own accumulator entry, so the second text block subtracts
    # the second entry rather than the first's text.
    events = _map_all(
        [
            _text_delta("First.", index=0),
            _text_delta("Second.", index=2),
            AssistantMessage(
                content=[
                    SdkTextBlock(text="First."),
                    SdkToolUseBlock(id="tu_2", name="Read", input={"path": "/tmp/x"}),
                    SdkTextBlock(text="Second. And a tail."),
                ],
                model="claude",
            ),
        ]
    )

    assert _joined(events) == "First.Second. And a tail."
    assert [e.tool_name for e in events if isinstance(e, ToolCall)] == ["Read"]


def test_a_block_the_sdk_parser_dropped_does_not_double_the_reply():
    # The SDK's message parser has no fallback case: a content block whose type
    # it does not recognise (``redacted_thinking``, or anything Anthropic adds
    # later) is silently dropped instead of appended. The finished message then
    # holds FEWER blocks than the raw stream had indices — here text streamed at
    # raw indices 0 and 2, but the parsed content is only two blocks long. Matching
    # a text block by its position in the parsed content would look index 2 up as
    # index 1, find nothing streamed there, and emit the whole block on top of what
    # the reader already saw. Text blocks keep their relative ORDER either way, so
    # that is what the accumulator matches on.
    events = _map_all(
        [
            _text_delta("First.", index=0),
            # index 1 is the redacted_thinking block the parser will drop — it
            # produces no text delta of its own.
            _text_delta("Second.", index=2),
            AssistantMessage(
                content=[SdkTextBlock(text="First."), SdkTextBlock(text="Second.")],
                model="claude",
            ),
        ]
    )

    assert _joined(events) == "First.Second."


def test_non_text_stream_events_emit_nothing():
    state = ClaudeParseState()
    noise = [
        _raw({"type": "message_start", "message": {"id": "msg_1"}}),
        _raw({"type": "content_block_start", "index": 0, "content_block": {"type": "text"}}),
        _raw(
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "hmm"},
            }
        ),
        _raw(
            {
                "type": "content_block_delta",
                "index": 1,
                "delta": {"type": "input_json_delta", "partial_json": '{"a":'},
            }
        ),
        _raw({"type": "content_block_stop", "index": 0}),
        _raw({"type": "message_delta", "delta": {"stop_reason": "end_turn"}}),
        _raw({"type": "message_stop"}),
        # A sub-agent's text is not this message's text.
        _text_delta("subagent chatter", parent="tu_parent"),
    ]
    assert _map_all(noise, state) == []
    # None of it reached the accumulator, so a finished block still emits whole.
    assert state.stream_text == []
    assert (
        _joined(
            _map_all([AssistantMessage(content=[SdkTextBlock(text="hi")], model="claude")], state)
        )
        == "hi"
    )


@pytest.mark.asyncio
async def test_adapter_asks_the_sdk_for_partial_messages():
    # Without this the SDK yields only whole AssistantMessages and a channel's
    # live surface has nothing to grow — the whole reply lands at once.
    factory = _Factory(_basic_messages())
    adapter = _adapter(factory)
    await _collect(adapter, _user_turn("hi"))
    assert factory.last_options is not None
    assert factory.last_options.include_partial_messages is True


@pytest.mark.asyncio
async def test_a_streamed_turn_reaches_a_consumer_exactly_once():
    messages = [
        SystemMessage(subtype="init", data={"session_id": "sess-1"}),
        _text_delta("One "),
        _text_delta("moment."),
        AssistantMessage(content=[SdkTextBlock(text="One moment.")], model="claude"),
        ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id="sess-1",
            usage={"input_tokens": 3, "output_tokens": 2},
            total_cost_usd=0.0,
        ),
    ]
    factory = _Factory(messages)
    adapter = _adapter(factory)
    events = await _collect(adapter, _user_turn("hello"))

    deltas = [e.text for e in events if isinstance(e, TextDelta)]
    assert deltas == ["One ", "moment."]  # streamed, not one lump at the end
    assert "".join(deltas) == "One moment."  # and the reply is not doubled
    assert isinstance(events[-1], TurnDone)


# ---------------------------------------------------------------------------
# Adapter — full turn streaming
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adapter_streams_events_and_persists_session():
    saved: list[str] = []

    async def on_session(sid: str) -> None:
        saved.append(sid)

    factory = _Factory(_basic_messages())
    adapter = _adapter(factory, on_session=on_session)
    events = await _collect(adapter, _user_turn("what files?"))

    assert isinstance(events[0], TurnStarted)
    assert isinstance(events[-1], TurnDone)
    deltas = [e.text for e in events if isinstance(e, TextDelta)]
    assert deltas == ["Let me check.", "There is one file."]
    assert [type(e) for e in events].count(TurnDone) == 1
    assert saved == ["sess-1"]
    assert factory.session is not None
    assert factory.session.connected_prompt == "what files?"
    assert factory.session.disconnected is True


@pytest.mark.asyncio
async def test_adapter_empty_prompt_is_rejected():
    factory = _Factory([])
    adapter = _adapter(factory)
    events = await _collect(adapter, [])
    assert len(events) == 1
    assert isinstance(events[0], TurnError)
    assert events[0].code == "empty_prompt"


@pytest.mark.asyncio
async def test_adapter_runs_with_bypass_permissions():
    factory = _Factory(_basic_messages())
    adapter = _adapter(factory)
    await _collect(adapter, _user_turn("hi"))
    assert factory.last_options is not None
    # Agents always run unattended: full permissions, no per-tool relay.
    assert factory.last_options.permission_mode == "bypassPermissions"
    assert factory.last_options.cwd == "/tmp"


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_interrupts_disconnects_and_persists_session():
    saved: list[str] = []

    async def on_session(sid: str) -> None:
        saved.append(sid)

    # Stream the init (so session_id is captured) then hang, so the turn can be
    # cancelled mid-stream at a known point.
    factory = _Factory(_basic_messages(), block_after=0)
    adapter = _adapter(factory, on_session=on_session)

    stream = await adapter.run_turn(history=_user_turn("go"))

    async def consume() -> None:
        async for _ in stream:
            pass

    task = asyncio.create_task(consume())
    # Let the stream capture the init message and reach the hang.
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert factory.session is not None
    assert factory.session.interrupted is True
    assert factory.session.disconnected is True
    assert saved == ["sess-1"]  # session persisted even on interruption


@pytest.mark.asyncio
async def test_stream_end_without_terminal_synthesizes_turn_done():
    # No ResultMessage in the stream — adapter must synthesize a terminal.
    messages = [
        SystemMessage(subtype="init", data={"session_id": "s2"}),
        AssistantMessage(content=[SdkTextBlock(text="hi")], model="claude"),
    ]
    factory = _Factory(messages)
    adapter = _adapter(factory)
    events = await _collect(adapter, _user_turn("hello"))
    terminals = [e for e in events if isinstance(e, (TurnDone, TurnError))]
    assert len(terminals) == 1
    assert isinstance(terminals[0], TurnDone)


# ---------------------------------------------------------------------------
# Pump error — exactly one terminal (issue #1)
# ---------------------------------------------------------------------------


class _ErrorSdkSession:
    """A fake SDK session whose ``receive_messages`` raises mid-stream."""

    def __init__(self, options: ClaudeAgentOptions) -> None:
        self.options = options
        self.connected_prompt: str | list[dict[str, Any]] | None = None
        self.disconnected = False

    async def connect(self, prompt: str | list[dict[str, Any]]) -> None:
        self.connected_prompt = prompt

    async def receive_messages(self) -> AsyncIterator[Any]:
        yield SystemMessage(subtype="init", data={"session_id": "err-sess"})
        raise RuntimeError("SDK stream exploded")

    async def interrupt(self) -> None:
        pass

    async def disconnect(self) -> None:
        self.disconnected = True


@pytest.mark.asyncio
async def test_pump_error_yields_exactly_one_terminal_turn_error():
    """A mid-stream pump exception must emit exactly one TurnError and NO
    trailing TurnDone (the double-terminal bug in the original code)."""
    session: _ErrorSdkSession | None = None

    def factory(options: ClaudeAgentOptions) -> _ErrorSdkSession:
        nonlocal session
        session = _ErrorSdkSession(options)
        return session

    adapter = ClaudeSdkAgentAdapter(
        cwd="/tmp",
        resume_session=None,
        extra={},
        session_factory=factory,
        on_session=_dummy_sink,
    )
    events = await _collect(adapter, _user_turn("go"))
    terminals = [e for e in events if isinstance(e, (TurnDone, TurnError))]
    assert len(terminals) == 1, f"expected 1 terminal, got {len(terminals)}: {terminals}"
    assert isinstance(terminals[0], TurnError)
    assert terminals[0].code == "sdk_stream_error"
    assert "exploded" in terminals[0].message
    assert session is not None
    assert session.disconnected is True


# ---------------------------------------------------------------------------
# env forwarding (issue #2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adapter_forwards_env_to_options():
    """env passed to the ctor must appear in the ClaudeAgentOptions."""
    factory = _Factory(_basic_messages())
    env = {"MY_VAR": "hello"}
    adapter = ClaudeSdkAgentAdapter(
        cwd="/tmp",
        resume_session=None,
        extra={},
        session_factory=factory,
        on_session=_dummy_sink,
        env=env,
    )
    await _collect(adapter, _user_turn("hi"))
    assert factory.last_options is not None
    assert factory.last_options.env == env


@pytest.mark.asyncio
async def test_adapter_omits_env_from_options_when_none():
    """When env is not provided to the adapter, the options.env must be the
    ClaudeAgentOptions default (empty dict) — i.e., we must not pass env=None
    explicitly, which would override the SDK default."""
    factory = _Factory(_basic_messages())
    adapter = _adapter(factory)  # no env kwarg
    await _collect(adapter, _user_turn("hi"))
    assert factory.last_options is not None
    # ClaudeAgentOptions.env defaults to {} via default_factory=dict.
    # When self._env is None we skip the kwarg entirely, so the default applies.
    assert factory.last_options.env == {}


# ---------------------------------------------------------------------------
# Resume-failure fallback (spec channels) — a poisoned session id must not brick
# conversation. A turn that never persisted a session (e.g. a /model slash
# command the CLI rejects in headless mode) leaves an id the CLI can't resume,
# so every later --resume exits non-zero; the adapter retries fresh.
# ---------------------------------------------------------------------------


class _FailingSdkSession:
    """A session whose connect() fails — mimics the CLI exiting non-zero (e.g.
    ``--resume`` of a session it can't find)."""

    def __init__(self, options: ClaudeAgentOptions) -> None:
        self.options = options
        self.disconnected = False

    async def connect(self, prompt: str | list[dict[str, Any]]) -> None:
        raise RuntimeError("Command failed with exit code 1")

    async def receive_messages(self) -> AsyncIterator[Any]:
        for _ in ():  # pragma: no cover - connect fails first
            yield _

    async def interrupt(self) -> None: ...

    async def disconnect(self) -> None:
        self.disconnected = True


@dataclass
class _ResumeThenFreshFactory:
    """First built session (carrying a resume) fails to connect; the second
    (fresh, resume=None) replays the basic stream."""

    messages: list[Any]
    options_seen: list[ClaudeAgentOptions] = field(default_factory=list, init=False)

    def __call__(self, options: ClaudeAgentOptions) -> Any:
        self.options_seen.append(options)
        if len(self.options_seen) == 1:
            return _FailingSdkSession(options)
        return FakeSdkSession(options, self.messages)


@pytest.mark.asyncio
async def test_resume_failure_falls_back_to_fresh_session():
    factory = _ResumeThenFreshFactory(_basic_messages())
    saved: list[str] = []

    async def sink(sid: str) -> None:
        saved.append(sid)

    adapter = _adapter(factory, on_session=sink, resume="poisoned-session-id")
    events = await _collect(adapter, _user_turn("hi"))

    # Two sessions built: first resumed the poisoned id, second went fresh.
    assert len(factory.options_seen) == 2
    assert factory.options_seen[0].resume == "poisoned-session-id"
    assert factory.options_seen[1].resume is None
    # The turn recovered: real events, no TurnError, terminal TurnDone.
    assert any(isinstance(e, TurnStarted) for e in events)
    assert any(isinstance(e, TextDelta) for e in events)
    assert not any(isinstance(e, TurnError) for e in events)
    assert isinstance(events[-1], TurnDone)
    # The fresh session id replaces the poisoned one.
    assert saved == ["sess-1"]


@dataclass
class _AlwaysFailFactory:
    calls: int = field(default=0, init=False)

    def __call__(self, options: ClaudeAgentOptions) -> Any:
        self.calls += 1
        return _FailingSdkSession(options)


@pytest.mark.asyncio
async def test_connect_failure_without_resume_yields_turn_error():
    factory = _AlwaysFailFactory()
    adapter = _adapter(factory, resume=None)
    events = await _collect(adapter, _user_turn("hi"))
    # No resume to drop → no retry; a single TurnError, not an unhandled raise.
    assert factory.calls == 1
    errs = [e for e in events if isinstance(e, TurnError)]
    assert len(errs) == 1
    assert errs[0].code == "sdk_connect_error"
    assert "failed to start" in errs[0].message
