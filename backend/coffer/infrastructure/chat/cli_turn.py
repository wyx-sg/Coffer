"""One turn of an agent driven through its own one-shot command line (spec chat
"Run a turn through the agent's one-shot command"; ADR
cursor-opencode-and-deepseek-harness-chat-through-their-one-shot-commands).

OpenCode (``opencode run --format json``), Cursor (``cursor-agent -p
--output-format stream-json``) and DeepSeek Harness (``dsh --profile headless
--json``) each answer one message per process and print one JSON object per
line while they work. What differs between them is the command and the shape
of a line; both live in the agent's own module as a :class:`CliAgent`. This
module is the part they share: spawn the process, read its lines, hand each to
the agent's :class:`CliMapper`, and end the turn honestly however the process
ended.

The process runs with the agent's full permissions, as Claude Code and Codex
do: the owner driving the conversation is the trust boundary.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import pathlib
import re
import shutil
import tempfile
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from coffer.domain.chat.attachment import Attachment, attachments_block
from coffer.domain.chat.events import (
    STREAM_ENDED,
    STREAM_ENDED_MESSAGE,
    AgentEvent,
    MessageEnd,
    TextDelta,
    ToolCall,
    ToolResult,
    TurnDone,
    TurnError,
    TurnProgress,
    TurnStarted,
)
from coffer.infrastructure.chat.adapter_support import SessionSink, attachment_note
from coffer.infrastructure.chat.transcribe import (
    Transcriber,
    prompt_with_transcripts,
    transcribe_audio_attachments,
)
from coffer.infrastructure.daemon.child_process import ChildProcess

_logger = logging.getLogger(__name__)

#: How much of the agent's stderr a failed turn quotes.
_STDERR_TAIL = 2_000
#: Read size for the agent's stdout; lines are split here, so a long tool
#: result is never refused by a line-length limit.
_CHUNK = 65_536
#: What a refused resume says, across the three CLIs: an id the agent no longer
#: has is retried once as a fresh session (spec chat "Retry a forgotten resume
#: id once as a fresh session").
_FORGOTTEN = re.compile(r"not found|unknown session|no such session|does not exist", re.I)


@dataclass
class TurnPlan:
    """How to run one turn: the command, what goes on its stdin (``None`` ⇒
    nothing; the CLIs that read a piped stdin as the message must see EOF),
    and the environment it adds."""

    argv: list[str]
    stdin: str | None = None
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class CliState:
    """What a turn learns while its lines arrive."""

    session_id: str | None = None
    model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    terminal: bool = False
    #: Whether anything the person would see has arrived (text, a tool).
    visible: bool = False
    tool_names: dict[str, str] = field(default_factory=dict)

    def add_tokens(self, prompt: object, completion: object) -> None:
        if isinstance(prompt, int):
            self.prompt_tokens = (self.prompt_tokens or 0) + prompt
        if isinstance(completion, int):
            self.completion_tokens = (self.completion_tokens or 0) + completion

    def done(self, stop_reason: str = "end_turn") -> TurnDone:
        self.terminal = True
        return TurnDone(
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            stop_reason=stop_reason,
        )

    def error(self, code: str, message: str) -> TurnError:
        self.terminal = True
        return TurnError(code=code, message=message)

    def text(self, text: str) -> list[AgentEvent]:
        """One whole message: these CLIs print a message once it is complete."""
        if not text:
            return []
        self.visible = True
        return [TextDelta(text=text), MessageEnd()]

    def tool_call(self, call_id: str, name: str, tool_input: object) -> ToolCall:
        self.visible = True
        self.tool_names[call_id] = name
        return ToolCall(
            tool_use_id=call_id,
            tool_name=name,
            tool_input=tool_input if isinstance(tool_input, dict) else {"input": tool_input},
        )

    def tool_result(self, call_id: str, output: object, error: str | None) -> ToolResult:
        return ToolResult(
            tool_use_id=call_id,
            tool_name=self.tool_names.get(call_id, ""),
            output=None if error else (output if isinstance(output, dict) else {"output": output}),
            error=error,
        )


def obj(value: object) -> dict[str, Any]:
    """``value`` when it is a JSON object, else an empty one."""
    return value if isinstance(value, dict) else {}


class CliMapper(Protocol):
    """Turns the agent's lines into events. One per turn."""

    def map(self, event: dict[str, Any], state: CliState) -> list[AgentEvent]: ...


class CliAgent(Protocol):
    """What one agent's module supplies: its command and its line shape."""

    agent_key: str
    #: The pidfile prefix of the turn's process (the orphan sweep reads it).
    process_name: str

    async def plan(
        self,
        *,
        binary: str,
        prompt: str,
        model: str | None,
        resume: str | None,
        system_context: str,
        scratch: pathlib.Path,
    ) -> TurnPlan: ...

    def mapper(self) -> CliMapper: ...


def _stderr_message(stderr: bytes, returncode: int | None) -> str:
    tail = stderr.decode("utf-8", "replace").strip()[-_STDERR_TAIL:]
    return tail or f"the agent exited with status {returncode}"


class CliTurnAdapter:
    """``AgentAdapter`` for one turn of a one-shot CLI agent."""

    def __init__(
        self,
        *,
        agent: CliAgent,
        binary: str,
        cwd: str,
        env: dict[str, str],
        model: str | None,
        resume_session: str | None,
        on_session: SessionSink,
        system_context: str = "",
        transcriber: Transcriber | None = None,
    ) -> None:
        self._agent = agent
        self._binary = binary
        self._cwd = cwd
        self._env = env
        self._model = model
        self._resume = resume_session
        self._on_session = on_session
        self._system_context = system_context
        self._transcriber = transcriber
        #: The model the turn ran on: what the agent reported, else what Coffer
        #: asked for.
        self.model_id: str | None = model

    async def run_turn(
        self, prompt: str, attachments: Sequence[Attachment] = ()
    ) -> AsyncIterator[AgentEvent]:
        return self._stream(prompt, attachments)

    async def _message(self, prompt: str, attachments: Sequence[Attachment]) -> str:
        # None of these agents hears audio: voice becomes text when the owner
        # opted in; every other file reaches the agent as its path.
        attachments, transcripts = await transcribe_audio_attachments(
            attachments, self._transcriber
        )
        prompt = prompt_with_transcripts(prompt.strip(), transcripts)
        if attachments:
            notes = attachments_block([attachment_note(a) for a in attachments])
            prompt = f"{prompt}\n\n{notes}".strip() if prompt else notes
        return prompt

    async def _persist(self, state: CliState) -> None:
        if not state.session_id or state.session_id == self._resume:
            return
        try:
            await self._on_session(state.session_id)
        except Exception:
            _logger.warning(
                "cli_turn.session_persist_failed",
                extra={"agent": self._agent.agent_key, "session_id": state.session_id},
                exc_info=True,
            )

    async def _stream(
        self, prompt: str, attachments: Sequence[Attachment]
    ) -> AsyncIterator[AgentEvent]:
        message = await self._message(prompt, attachments)
        if not message:
            yield TurnError(code="empty_prompt", message="no user message to send")
            return
        yield TurnStarted()
        scratch = pathlib.Path(tempfile.mkdtemp(prefix=f"coffer-{self._agent.process_name}-"))
        try:
            resume = self._resume
            while True:
                retry = False
                async for item in self._run_once(message, resume, scratch):
                    if item is _RETRY_FRESH:
                        retry = True
                        break
                    yield item
                if not retry:
                    return
                _logger.warning(
                    "cli_turn.resume_forgotten_retrying_fresh",
                    extra={"agent": self._agent.agent_key, "resume": resume},
                )
                resume = None
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    async def _run_once(
        self, message: str, resume: str | None, scratch: pathlib.Path
    ) -> AsyncIterator[Any]:
        state = CliState(session_id=resume)
        mapper = self._agent.mapper()
        plan = await self._agent.plan(
            binary=self._binary,
            prompt=message,
            model=self._model,
            resume=resume,
            system_context=self._system_context,
            scratch=scratch,
        )
        # Merged with the daemon's own environment: a spawn REPLACES it.
        # ``PWD`` follows the turn's folder: OpenCode takes its project folder
        # from ``PWD`` rather than the process's directory, and would otherwise
        # work in the daemon's.
        env = {**os.environ, **self._env, **plan.env, "PWD": self._cwd}
        # stderr goes to a file: read once the process has ended, and no task
        # has to drain it meanwhile.
        err_path = scratch / f"stderr-{uuid.uuid4().hex}.txt"
        err_file = err_path.open("wb")
        try:
            child = await ChildProcess.spawn(
                self._agent.process_name,
                plan.argv,
                cwd=self._cwd,
                env=env,
                stdin=(
                    asyncio.subprocess.PIPE
                    if plan.stdin is not None
                    else asyncio.subprocess.DEVNULL
                ),
                stdout=asyncio.subprocess.PIPE,
                stderr=err_file.fileno(),
            )
        except OSError as exc:
            yield state.error(f"{self._agent.process_name}_start_failed", str(exc))
            return
        finally:
            err_file.close()
        proc = child.process
        held: TurnError | None = None
        try:
            if plan.stdin is not None and proc.stdin is not None:
                with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                    proc.stdin.write(plan.stdin.encode())
                    await proc.stdin.drain()
                proc.stdin.close()
            async for line in _lines(proc.stdout):
                if state.terminal:
                    # Drained, not read: a child blocked on a full pipe never exits.
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    # A line that is not an event (a CLI's own notice): a sign
                    # of life for the idle watchdog, nothing to show.
                    yield TurnProgress()
                    continue
                if not isinstance(event, dict):
                    continue
                events = mapper.map(event, state) or [TurnProgress()]
                if state.model:
                    self.model_id = state.model
                for out in events:
                    if isinstance(out, TurnError) and resume and not state.visible:
                        # Maybe the stored session refused: decided at exit.
                        held = out
                        break
                    yield out
                    if isinstance(out, (TurnDone, TurnError)):
                        break
            returncode = await proc.wait()
            stderr = err_path.read_bytes() if err_path.exists() else b""
            said = stderr.decode("utf-8", "replace") + (held.message if held else "")
            if (
                resume
                and (held is not None or (not state.terminal and returncode != 0))
                and not state.visible
                and _FORGOTTEN.search(said)
            ):
                yield _RETRY_FRESH
                return
            if held is not None:
                yield held
            elif not state.terminal:
                if returncode == 0:
                    yield state.done()
                elif stderr.strip():
                    yield state.error(
                        f"{self._agent.process_name}_failed", _stderr_message(stderr, returncode)
                    )
                else:
                    yield state.error(STREAM_ENDED, STREAM_ENDED_MESSAGE)
            await self._persist(state)
        except asyncio.CancelledError:
            # Persist the session id on interruption too: it arrives on the
            # first line, so an interrupted turn stays resumable.
            await self._persist(state)
            raise
        finally:
            with contextlib.suppress(BaseException):
                await asyncio.shield(child.terminate())


#: Yielded by ``_run_once`` when the stored session id was refused before
#: anything was shown: the turn is run once more as a fresh session.
_RETRY_FRESH = object()


async def _lines(stream: asyncio.StreamReader | None) -> AsyncIterator[str]:
    if stream is None:
        return
    buffer = b""
    while True:
        chunk = await stream.read(_CHUNK)
        if not chunk:
            break
        buffer += chunk
        *complete, buffer = buffer.split(b"\n")
        for raw in complete:
            text = raw.decode("utf-8", "replace").strip()
            if text:
                yield text
    tail = buffer.decode("utf-8", "replace").strip()
    if tail:
        yield tail


__all__ = ["CliAgent", "CliMapper", "CliState", "CliTurnAdapter", "TurnPlan", "obj"]
