"""SDK-backed Claude adapter — drive Claude Code via ``claude-agent-sdk``.

Unlike ``cli_agent.py`` (which shells out to ``claude -p``), this adapter drives
Claude Code through the Python ``ClaudeSDKClient``. The agent runs with full
permissions (``bypassPermissions``): Coffer does not gate individual tool calls —
the paired owner driving the conversation is the trust boundary.

Streamed messages feed an ``asyncio.Queue``; ``_stream`` drains it into
``AgentEvent``s. The concrete ``ClaudeSDKClient`` is wrapped behind the
``ClaudeSdkSession`` protocol so turns are testable without a real ``claude``
binary. Per Contract 9 this file is the only one that imports the real
``ClaudeSDKClient``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any, Protocol

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
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
    AgentEvent,
    TextDelta,
    ToolCall,
    ToolResult,
    TurnDone,
    TurnError,
    TurnStarted,
)
from coffer.domain.chat.message import Message
from coffer.infrastructure.chat.cli_agent import ParseState, SessionSink, last_user_text

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Session injection seam
# ---------------------------------------------------------------------------


class ClaudeSdkSession(Protocol):
    """The thin slice of ``ClaudeSDKClient`` the adapter drives, behind a seam.

    Injected via :data:`SdkSessionFactory` so turns can be tested with a fake
    session that replays canned SDK messages (mirrors ``cli_agent``'s
    ``CliProcess`` / ``Spawner`` split).
    """

    async def connect(self, prompt: str) -> None: ...

    def receive_messages(self) -> AsyncIterator[Any]: ...

    async def interrupt(self) -> None: ...

    async def disconnect(self) -> None: ...


#: Build one SDK session from its options: ``(options) -> ClaudeSdkSession``.
SdkSessionFactory = Callable[[ClaudeAgentOptions], ClaudeSdkSession]


class ClaudeSdkClientSession:
    """Adapts the real ``ClaudeSDKClient`` to the ``ClaudeSdkSession`` protocol.

    Kept deliberately thin — the only place the concrete SDK client is touched —
    so the rest of the adapter stays unit-testable behind the protocol.
    """

    def __init__(self, options: ClaudeAgentOptions) -> None:
        self._client = ClaudeSDKClient(options=options)

    async def connect(self, prompt: str) -> None:
        # Pass the single user turn as a one-message async stream rather than a
        # plain string (the SDK streams it, waits for the result, then ends
        # input).
        async def _stream() -> AsyncIterator[dict[str, Any]]:
            msg = {"role": "user", "content": prompt}
            yield {"type": "user", "session_id": "", "message": msg, "parent_tool_use_id": None}

        await self._client.connect(_stream())

    def receive_messages(self) -> AsyncIterator[Any]:
        return self._client.receive_messages()

    async def interrupt(self) -> None:
        await self._client.interrupt()

    async def disconnect(self) -> None:
        await self._client.disconnect()


def default_session_factory(options: ClaudeAgentOptions) -> ClaudeSdkSession:
    """Build a real ``ClaudeSDKClient``-backed session (production seam)."""
    return ClaudeSdkClientSession(options)


# ---------------------------------------------------------------------------
# Message mapping — SDK message objects -> AgentEvent
# ---------------------------------------------------------------------------


def map_sdk_message(msg: Any, state: ParseState) -> list[AgentEvent]:
    """Map one streamed SDK message to zero or more ``AgentEvent``s.

    The SDK analog of ``ClaudeCodeDialect.parse``: ``SystemMessage(init)``
    captures the session id; ``AssistantMessage`` yields text/tool-call events;
    ``UserMessage`` carries tool results; ``ResultMessage`` is terminal.
    """
    if isinstance(msg, SystemMessage):
        if msg.subtype == "init":
            state.session_id = (msg.data or {}).get("session_id") or state.session_id
        return []
    if isinstance(msg, AssistantMessage):
        return _assistant_blocks(msg, state)
    if isinstance(msg, UserMessage):
        return _tool_results(msg, state)
    if isinstance(msg, ResultMessage):
        return _result(msg, state)
    return []


def _assistant_blocks(msg: AssistantMessage, state: ParseState) -> list[AgentEvent]:
    out: list[AgentEvent] = []
    for block in msg.content:
        if isinstance(block, SdkTextBlock):
            if block.text:
                out.append(TextDelta(text=block.text))
        elif isinstance(block, SdkToolUseBlock):
            tid = str(block.id)
            name = str(block.name)
            state.tool_names[tid] = name
            out.append(ToolCall(tool_use_id=tid, tool_name=name, tool_input=block.input or {}))
    return out


def _tool_results(msg: UserMessage, state: ParseState) -> list[AgentEvent]:
    out: list[AgentEvent] = []
    content = msg.content
    if not isinstance(content, list):
        return out
    for block in content:
        if not isinstance(block, SdkToolResultBlock):
            continue
        tid = str(block.tool_use_id)
        is_error = bool(block.is_error)
        text = _stringify(block.content)
        out.append(
            ToolResult(
                tool_use_id=tid,
                tool_name=state.tool_names.get(tid, ""),
                output=None if is_error else {"content": text},
                error=text if is_error else None,
            )
        )
    return out


def _result(msg: ResultMessage, state: ParseState) -> list[AgentEvent]:
    usage = msg.usage or {}
    state.prompt_tokens = usage.get("input_tokens")
    state.completion_tokens = usage.get("output_tokens")
    state.terminal_emitted = True
    if msg.is_error or msg.subtype not in (None, "success"):
        return [
            TurnError(
                code="sdk_error",
                message=str(msg.result or msg.subtype or "claude sdk error"),
            )
        ]
    if msg.subtype is None:
        _logger.warning(
            "claude_sdk_agent.result_subtype_none",
            extra={"session_id": state.session_id, "stop_reason": msg.stop_reason},
        )
    return [
        TurnDone(
            prompt_tokens=state.prompt_tokens,
            completion_tokens=state.completion_tokens,
            stop_reason=str(msg.stop_reason or "end_turn"),
        )
    ]


def _stringify(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [c.get("text", "") if isinstance(c, dict) else str(c) for c in content]
        return "".join(parts)
    return str(content)


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

#: Sentinel pushed after the terminal event so ``_stream`` knows to stop.
_SENTINEL = object()


def _connect_error_message(exc: Exception) -> str:
    # The SDK's ProcessError swallows the CLI's stderr, so we surface the
    # exception text — still better than the orchestrator's "unexpected error".
    return f"the agent process failed to start: {exc}"


class ClaudeSdkAgentAdapter:
    """One turn of an SDK-backed Claude agent.

    Mirrors ``CliAgentAdapter``: an injected ``session_factory`` seam, a
    ``run_turn`` that returns ``self._stream(...)``, best-effort logged session
    persistence, and ``CancelledError`` cleanup that interrupts + disconnects the
    session and still persists the session id.
    """

    def __init__(
        self,
        *,
        cwd: str,
        resume_session: str | None,
        extra: dict[str, Any],
        session_factory: SdkSessionFactory,
        on_session: SessionSink,
        env: dict[str, str] | None = None,
    ) -> None:
        self._cwd = cwd
        self._resume = resume_session
        self._extra = extra
        self._session_factory = session_factory
        self._on_session = on_session
        self._env = env

    async def run_turn(
        self,
        *,
        history: Sequence[Message],
    ) -> AsyncIterator[AgentEvent]:
        # Match the platform's ``async def -> AsyncIterator`` seam: delegate to
        # ``_stream`` so the coroutine machinery runs at yield points rather than
        # at the ``await run_turn(...)`` call site (cli_agent does the same).
        return self._stream(history)

    async def _persist_session(self, state: ParseState) -> None:
        """Write a newly-discovered SDK session id back for the next ``resume``.

        Best-effort but logged (mirrors ``cli_agent``): a failed write only costs
        session continuity, so it must not fail the turn.
        """
        if not state.session_id or state.session_id == self._resume:
            return
        try:
            await self._on_session(state.session_id)
        except Exception:
            _logger.warning(
                "claude_sdk_agent.session_persist_failed",
                extra={"session_id": state.session_id},
                exc_info=True,
            )

    def _build_options(self, *, resume: str | None) -> ClaudeAgentOptions:
        # Run with full permissions — Coffer does not gate individual tool calls;
        # the paired owner driving the conversation is the trust boundary.
        opts = ClaudeAgentOptions(
            cwd=self._cwd,
            resume=resume,
            permission_mode="bypassPermissions",
            model=self._extra.get("model"),
        )
        if self._env is not None:
            opts.env = self._env
        return opts

    async def _connect(self, prompt: str, *, resume: str | None) -> ClaudeSdkSession:
        """Build a session and connect it; disconnect + re-raise on failure so a
        caller can retry cleanly."""
        session = self._session_factory(self._build_options(resume=resume))
        try:
            await session.connect(prompt)
        except Exception:
            with contextlib.suppress(Exception):
                await session.disconnect()
            raise
        return session

    async def _stream(self, history: Sequence[Message]) -> AsyncIterator[AgentEvent]:
        prompt = last_user_text(history)
        if not prompt:
            yield TurnError(code="empty_prompt", message="no user message to send")
            return

        state = ParseState(session_id=self._resume)
        queue: asyncio.Queue[Any] = asyncio.Queue()
        yield TurnStarted()

        # Connect, with a one-shot fallback to a fresh session when resuming a
        # session the CLI can't find (a prior turn — e.g. a rejected ``/model``
        # slash command — leaves an id that makes every later ``--resume`` exit
        # non-zero). The fallback keeps the conversation usable; a hard failure
        # becomes a TurnError rather than an unhandled "unexpected error".
        try:
            session = await self._connect(prompt, resume=self._resume)
        except Exception as exc:
            if self._resume is None:
                yield TurnError(code="sdk_connect_error", message=_connect_error_message(exc))
                return
            _logger.warning(
                "claude_sdk_agent.resume_failed_retrying_fresh",
                extra={"resume": self._resume},
                exc_info=True,
            )
            state = ParseState(session_id=None)
            try:
                session = await self._connect(prompt, resume=None)
            except Exception as exc2:
                yield TurnError(code="sdk_connect_error", message=_connect_error_message(exc2))
                return

        async def pump() -> None:
            # Map streamed SDK messages onto the queue. A sentinel after the
            # terminal event ends the drain.
            try:
                async for msg in session.receive_messages():
                    for event in map_sdk_message(msg, state):
                        await queue.put(event)
                        if isinstance(event, (TurnDone, TurnError)):
                            await queue.put(_SENTINEL)
                            return
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # surface pump failures as a terminal error
                state.terminal_emitted = True
                await queue.put(TurnError(code="sdk_stream_error", message=str(exc)))
            await queue.put(_SENTINEL)

        pump_task: asyncio.Task[None] | None = None
        try:
            pump_task = asyncio.create_task(pump())
            while True:
                item = await queue.get()
                if item is _SENTINEL:
                    break
                yield item
            await self._persist_session(state)
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                await session.interrupt()
            # Persist the session id even on interruption: the SDK emits it early
            # (its init message), so an interrupted turn stays resumable.
            await self._persist_session(state)
            raise
        finally:
            if pump_task is not None:
                pump_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await pump_task
            with contextlib.suppress(Exception):
                await session.disconnect()

        if not state.terminal_emitted:
            # The stream ended without a ResultMessage — synthesize a terminal
            # so the orchestrator never hangs waiting for one.
            yield TurnDone(
                prompt_tokens=state.prompt_tokens,
                completion_tokens=state.completion_tokens,
                stop_reason="end_turn",
            )


__all__ = [
    "ClaudeSdkAgentAdapter",
    "ClaudeSdkClientSession",
    "ClaudeSdkSession",
    "SdkSessionFactory",
    "default_session_factory",
    "map_sdk_message",
]
