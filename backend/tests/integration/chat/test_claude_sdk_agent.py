"""SDK-backed Claude adapter tests (spec 008).

Drives ``ClaudeSdkAgentAdapter`` through a ``FakeSdkSession`` that replays a
scripted list of SDK message objects. No real ``claude`` binary or network is
touched — everything goes through the fake. Agents always run with full
permissions (``permission_mode="bypassPermissions"``), so there is no per-tool
approval relay.
"""

from __future__ import annotations

import asyncio
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
    ClaudeSdkAgentAdapter,
    map_sdk_message,
)
from coffer.infrastructure.chat.cli_agent import ParseState

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
        self.connected_prompt: str | None = None
        self.interrupted = False
        self.disconnected = False

    async def connect(self, prompt: str) -> None:
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


def _adapter(
    factory: _Factory,
    *,
    on_session: Any = _dummy_sink,
    resume: str | None = None,
    extra: dict[str, Any] | None = None,
) -> ClaudeSdkAgentAdapter:
    return ClaudeSdkAgentAdapter(
        cwd="/tmp",
        resume_session=resume,
        extra=extra or {},
        session_factory=factory,
        on_session=on_session,
    )


async def _collect(adapter: ClaudeSdkAgentAdapter, history: list[Message]):
    stream = await adapter.run_turn(history=history)
    return [ev async for ev in stream]


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
    state = ParseState()
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
    state = ParseState()
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
    state = ParseState()
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
        self.connected_prompt: str | None = None
        self.disconnected = False

    async def connect(self, prompt: str) -> None:
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
