"""SDK-backed Claude adapter tests (spec 008 — per-tool approval relay).

Drives ``ClaudeSdkAgentAdapter`` through a ``FakeSdkSession`` that replays a
scripted list of SDK message objects and, at a scripted point, invokes the
adapter's injected ``can_use_tool`` callback to simulate a permission request.
No real ``claude`` binary or network is touched — everything goes through the
fake. The real ``ApprovalChannel`` resolves the relayed request so the full
approval round-trip (adapter → ApprovalRequest event → channel → callback
result) is exercised end to end.
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
    PermissionResultAllow,
    PermissionResultDeny,
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

from coffer.application.chat.approvals import ApprovalChannel
from coffer.application.chat.ports import ApprovalDecision
from coffer.domain.chat.events import (
    ApprovalRequest,
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


@dataclass
class _ApprovalScript:
    """Scripts one ``can_use_tool`` call the fake session makes mid-stream.

    ``after_index`` is the index into the scripted message list after which the
    fake invokes the adapter's ``can_use_tool`` (so the request interleaves with
    streamed messages, exactly as the real SDK dispatches control requests in a
    separate task).
    """

    after_index: int
    tool_name: str
    tool_input: dict[str, Any]
    tool_use_id: str | None
    result: PermissionResultAllow | PermissionResultDeny | None = None


class _FakeContext:
    """Stand-in for the SDK's ToolPermissionContext (only tool_use_id is read)."""

    def __init__(self, tool_use_id: str | None) -> None:
        self.tool_use_id = tool_use_id


class FakeSdkSession:
    """A ``ClaudeSdkSession`` that replays canned messages and optionally fires
    a scripted ``can_use_tool`` call partway through the stream."""

    def __init__(
        self,
        options: ClaudeAgentOptions,
        messages: list[Any],
        approval: _ApprovalScript | None = None,
        block_after: int | None = None,
    ) -> None:
        self.options = options
        self._messages = messages
        self._approval = approval
        # If set, the stream pauses on this event so a cancel can be injected.
        self._block_after = block_after
        self.connected_prompt: str | None = None
        self.interrupted = False
        self.disconnected = False
        # Tracks the spawned approval task so tests can await it after the stream.
        self.approval_task: asyncio.Task[None] | None = None

    async def connect(self, prompt: str) -> None:
        self.connected_prompt = prompt

    async def receive_messages(self) -> AsyncIterator[Any]:
        can_use_tool = self.options.can_use_tool
        for idx, msg in enumerate(self._messages):
            yield msg
            if self._approval is not None and idx == self._approval.after_index:
                assert can_use_tool is not None, "adapter must wire can_use_tool"
                ctx = _FakeContext(self._approval.tool_use_id)
                # Mirror the real SDK: fire the approval callback in its own task
                # so it runs concurrently with the message stream (the drain loop
                # must handle the ApprovalRequest event while can_use_tool awaits).
                approval = self._approval  # capture for closure

                async def _run_approval(
                    a: _ApprovalScript = approval, c: _FakeContext = ctx
                ) -> None:
                    a.result = await can_use_tool(a.tool_name, a.tool_input, c)

                self.approval_task = asyncio.create_task(_run_approval())
                # Yield control so the task is dispatched before the next message.
                await asyncio.sleep(0)
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
    approval: _ApprovalScript | None = None
    block_after: int | None = None
    last_options: ClaudeAgentOptions | None = field(default=None, init=False)
    session: FakeSdkSession | None = field(default=None, init=False)

    def __call__(self, options: ClaudeAgentOptions) -> FakeSdkSession:
        self.last_options = options
        self.session = FakeSdkSession(options, self.messages, self.approval, self.block_after)
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


class _NoApprovals:
    async def wait(self, request_id: str) -> ApprovalDecision:  # pragma: no cover
        raise AssertionError("this turn requests no approval")


async def _collect(adapter: ClaudeSdkAgentAdapter, history: list[Message], approvals: Any):
    stream = await adapter.run_turn(history=history, approvals=approvals)
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
    events = await _collect(adapter, _user_turn("what files?"), _NoApprovals())

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
    events = await _collect(adapter, [], _NoApprovals())
    assert len(events) == 1
    assert isinstance(events[0], TurnError)
    assert events[0].code == "empty_prompt"


@pytest.mark.asyncio
async def test_adapter_forces_default_permission_mode_for_relay():
    factory = _Factory(_basic_messages())
    adapter = _adapter(factory)
    await _collect(adapter, _user_turn("hi"), _NoApprovals())
    assert factory.last_options is not None
    # default mode is forced so the SDK routes tool calls through can_use_tool.
    assert factory.last_options.permission_mode == "default"
    assert factory.last_options.can_use_tool is not None
    assert factory.last_options.cwd == "/tmp"


@pytest.mark.asyncio
async def test_adapter_honors_explicit_permission_mode():
    factory = _Factory(_basic_messages())
    adapter = _adapter(factory, extra={"permission_mode": "plan", "model": "opus"})
    await _collect(adapter, _user_turn("hi"), _NoApprovals())
    assert factory.last_options is not None
    assert factory.last_options.permission_mode == "plan"
    assert factory.last_options.model == "opus"


# ---------------------------------------------------------------------------
# Approval relay — the heart of this task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approval_allow_relays_to_permission_result_allow():
    approval = _ApprovalScript(
        after_index=1, tool_name="Bash", tool_input={"command": "rm x"}, tool_use_id="tu_1"
    )
    factory = _Factory(_basic_messages(), approval=approval)
    adapter = _adapter(factory)
    channel = ApprovalChannel()

    async def drive() -> list[Any]:
        stream = await adapter.run_turn(history=_user_turn("delete"), approvals=channel)
        out = []
        async for ev in stream:
            out.append(ev)
            if isinstance(ev, ApprovalRequest):
                channel.resolve(ev.request_id, ApprovalDecision(behavior="allow"))
        return out

    events = await asyncio.wait_for(drive(), timeout=5)
    # Await the approval task so its result is visible before asserting.
    if factory.session and factory.session.approval_task is not None:
        await factory.session.approval_task

    reqs = [e for e in events if isinstance(e, ApprovalRequest)]
    assert len(reqs) == 1
    assert reqs[0].tool_name == "Bash"
    assert reqs[0].tool_input == {"command": "rm x"}
    assert reqs[0].tool_use_id == "tu_1"
    assert reqs[0].request_id == "tu_1"  # request_id derives from tool_use_id
    assert isinstance(approval.result, PermissionResultAllow)
    assert isinstance(events[-1], TurnDone)


@pytest.mark.asyncio
async def test_approval_deny_relays_to_permission_result_deny():
    approval = _ApprovalScript(
        after_index=1, tool_name="Bash", tool_input={"command": "rm -rf /"}, tool_use_id="tu_1"
    )
    factory = _Factory(_basic_messages(), approval=approval)
    adapter = _adapter(factory)
    channel = ApprovalChannel()

    async def drive() -> list[Any]:
        stream = await adapter.run_turn(history=_user_turn("delete"), approvals=channel)
        out = []
        async for ev in stream:
            out.append(ev)
            if isinstance(ev, ApprovalRequest):
                channel.resolve(ev.request_id, ApprovalDecision(behavior="deny", message="nope"))
        return out

    events = await asyncio.wait_for(drive(), timeout=5)
    # Await the approval task so its result is visible before asserting.
    if factory.session and factory.session.approval_task is not None:
        await factory.session.approval_task

    reqs = [e for e in events if isinstance(e, ApprovalRequest)]
    assert len(reqs) == 1
    assert isinstance(approval.result, PermissionResultDeny)
    assert approval.result.message == "nope"


@pytest.mark.asyncio
async def test_approval_without_tool_use_id_synthesizes_request_id():
    approval = _ApprovalScript(
        after_index=1, tool_name="Read", tool_input={"path": "/x"}, tool_use_id=None
    )
    factory = _Factory(_basic_messages(), approval=approval)
    adapter = _adapter(factory)
    channel = ApprovalChannel()

    async def drive() -> list[Any]:
        stream = await adapter.run_turn(history=_user_turn("read"), approvals=channel)
        out = []
        async for ev in stream:
            out.append(ev)
            if isinstance(ev, ApprovalRequest):
                channel.resolve(ev.request_id, ApprovalDecision(behavior="allow"))
        return out

    events = await asyncio.wait_for(drive(), timeout=5)
    # Await the approval task so its result is visible before asserting.
    if factory.session and factory.session.approval_task is not None:
        await factory.session.approval_task
    reqs = [e for e in events if isinstance(e, ApprovalRequest)]
    assert len(reqs) == 1
    assert reqs[0].request_id  # a synthesized id is present
    assert reqs[0].tool_use_id == reqs[0].request_id  # mirrors the request id


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
    channel = ApprovalChannel()

    stream = await adapter.run_turn(history=_user_turn("go"), approvals=channel)

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
    events = await _collect(adapter, _user_turn("hello"), _NoApprovals())
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
    events = await _collect(adapter, _user_turn("go"), _NoApprovals())
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
    await _collect(adapter, _user_turn("hi"), _NoApprovals())
    assert factory.last_options is not None
    assert factory.last_options.env == env


@pytest.mark.asyncio
async def test_adapter_omits_env_from_options_when_none():
    """When env is not provided to the adapter, the options.env must be the
    ClaudeAgentOptions default (empty dict) — i.e., we must not pass env=None
    explicitly, which would override the SDK default."""
    factory = _Factory(_basic_messages())
    adapter = _adapter(factory)  # no env kwarg
    await _collect(adapter, _user_turn("hi"), _NoApprovals())
    assert factory.last_options is not None
    # ClaudeAgentOptions.env defaults to {} via default_factory=dict.
    # When self._env is None we skip the kwarg entirely, so the default applies.
    assert factory.last_options.env == {}
