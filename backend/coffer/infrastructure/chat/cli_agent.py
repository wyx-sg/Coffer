"""CLI-agent adapter — drive an installed coding CLI (Claude Code, Codex) as a
chat agent behind the platform seam (spec 008).

A turn spawns the agent's CLI in a user-chosen working directory, streams its
line-delimited JSON output, and maps each line to the platform's ``AgentEvent``
union via a per-product :class:`CliDialect`. The CLI session id it reports is
written back to the conversation's ``agent_config`` so the next turn resumes the
same session. The subprocess spawner is injected so turns can be tested without
a real CLI installed.

v1 does not bridge per-tool approval: the CLI runs under its own permission mode
(configurable, default conservative). Approval bridging is a later increment.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from coffer.application.chat.ports import ApprovalGate
from coffer.domain.chat.events import (
    AgentEvent,
    TurnDone,
    TurnError,
    TurnStarted,
)
from coffer.domain.chat.message import Message, Role, TextBlock

_logger = logging.getLogger(__name__)


class CliProcess(Protocol):
    """A spawned CLI process the adapter streams and can terminate."""

    def stdout_lines(self) -> AsyncIterator[str]:
        """Yield decoded stdout lines until the process closes its stream."""
        ...

    async def wait(self) -> int:
        """Await exit and return the process return code."""
        ...

    def terminate(self) -> None:
        """Best-effort terminate (used on turn cancellation)."""
        ...


#: Spawn one CLI process: ``(argv, cwd, env) -> CliProcess``.
Spawner = Callable[[Sequence[str], str, dict[str, str] | None], Awaitable[CliProcess]]

#: Persist a discovered CLI session id back onto the conversation.
SessionSink = Callable[[str], Awaitable[None]]


@dataclass
class ParseState:
    """Mutable state threaded through a dialect's per-line parsing."""

    session_id: str | None = None
    tool_names: dict[str, str] = field(default_factory=dict)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    terminal_emitted: bool = False


class CliDialect(Protocol):
    """A product-specific command builder + output parser."""

    binary: str

    def build_argv(
        self, prompt: str, *, resume_session: str | None, extra: dict[str, Any]
    ) -> list[str]:
        """Build the CLI argv for one turn."""
        ...

    def parse(self, line: dict[str, Any], state: ParseState) -> list[AgentEvent]:
        """Map one parsed JSON output line to zero or more ``AgentEvent``s."""
        ...


def last_user_text(history: Sequence[Message]) -> str:
    """The text of the most recent user message — the prompt for this turn."""
    for msg in reversed(history):
        if msg.role is Role.USER:
            return "".join(b.text for b in msg.content if isinstance(b, TextBlock)).strip()
    return ""


async def default_spawner(argv: Sequence[str], cwd: str, env: dict[str, str] | None) -> CliProcess:
    """Spawn a real subprocess via asyncio, streaming stdout line by line."""
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    return _AsyncSubprocess(proc)


class _AsyncSubprocess:
    """Adapts ``asyncio.subprocess.Process`` to the ``CliProcess`` protocol."""

    def __init__(self, proc: asyncio.subprocess.Process) -> None:
        self._proc = proc

    async def stdout_lines(self) -> AsyncIterator[str]:
        assert self._proc.stdout is not None
        async for raw in self._proc.stdout:
            yield raw.decode("utf-8", errors="replace")

    async def wait(self) -> int:
        return await self._proc.wait()

    def terminate(self) -> None:
        with contextlib.suppress(ProcessLookupError):
            self._proc.terminate()


class CliAgentAdapter:
    """One turn of a CLI-backed agent. Self-contained per the ``AgentAdapter`` seam."""

    def __init__(
        self,
        *,
        dialect: CliDialect,
        cwd: str,
        resume_session: str | None,
        extra: dict[str, Any],
        spawn: Spawner,
        on_session: SessionSink,
        env: dict[str, str] | None = None,
    ) -> None:
        self._dialect = dialect
        self._cwd = cwd
        self._resume = resume_session
        self._extra = extra
        self._spawn = spawn
        self._on_session = on_session
        self._env = env

    async def run_turn(
        self,
        *,
        history: Sequence[Message],
        approvals: ApprovalGate,
    ) -> AsyncIterator[AgentEvent]:
        # Match the platform's ``async def -> AsyncIterator`` seam: return the
        # async generator rather than being one (the builtin adapter does the same).
        return self._stream(history)

    async def _persist_session(self, state: ParseState) -> None:
        """Write a newly-discovered CLI session id back for the next --resume.

        Best-effort but NOT silent: a failed write only costs session continuity,
        so it must not fail the turn — but it is logged so the loss is diagnosable.
        """
        if not state.session_id or state.session_id == self._resume:
            return
        try:
            await self._on_session(state.session_id)
        except Exception:
            _logger.warning(
                "cli_agent.session_persist_failed",
                extra={"session_id": state.session_id},
                exc_info=True,
            )

    async def _stream(self, history: Sequence[Message]) -> AsyncIterator[AgentEvent]:
        prompt = last_user_text(history)
        if not prompt:
            yield TurnError(code="empty_prompt", message="no user message to send")
            return

        argv = self._dialect.build_argv(prompt, resume_session=self._resume, extra=self._extra)
        state = ParseState(session_id=self._resume)
        yield TurnStarted()

        proc = await self._spawn(argv, self._cwd, self._env)
        try:
            async for raw in proc.stdout_lines():
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue  # ignore non-JSON noise on stdout
                if not isinstance(obj, dict):
                    continue
                for event in self._dialect.parse(obj, state):
                    yield event
            code = await proc.wait()
        except asyncio.CancelledError:
            proc.terminate()
            with contextlib.suppress(Exception):
                await proc.wait()
            # Persist the session id even on interruption: the CLI emits it early
            # (its init line), so an interrupted turn must still be resumable.
            await self._persist_session(state)
            raise

        # Persist the (possibly new) session id so the next turn can --resume it.
        await self._persist_session(state)

        if not state.terminal_emitted:
            # The CLI closed without a result line — synthesize a terminal event
            # so the orchestrator never hangs waiting for one.
            if code == 0:
                yield TurnDone(
                    prompt_tokens=state.prompt_tokens,
                    completion_tokens=state.completion_tokens,
                    stop_reason="end_turn",
                )
            else:
                yield TurnError(
                    code="cli_exit",
                    message=f"{self._dialect.binary} exited with code {code}",
                )


__all__ = [
    "CliAgentAdapter",
    "CliDialect",
    "CliProcess",
    "ParseState",
    "SessionSink",
    "Spawner",
    "default_spawner",
    "last_user_text",
]
