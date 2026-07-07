"""``opencode run``-backed adapter — one ``AgentAdapter`` turn per subprocess.

Structurally simpler than :class:`CodexAppServerAdapter`: opencode's headless run
mode is a per-turn subprocess (``opencode run --format json``) whose stdout is a
line-delimited stream of message parts, so there is no persistent app-server or
JSON-RPC session to manage. The adapter spawns the process, maps each stdout line
via :func:`map_opencode_event`, and synthesises the terminal ``TurnDone`` /
``TurnError`` on process exit. The upstream session id (for ``--session`` resume)
is discovered from the stream and persisted via ``on_session``.

Only stdlib ``asyncio`` + ``json`` are used — no third-party dependency.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator, Sequence

from coffer.domain.chat.attachment import Attachment
from coffer.domain.chat.events import AgentEvent, TurnDone, TurnError, TurnStarted
from coffer.domain.chat.message import Message
from coffer.infrastructure.chat.adapter_support import SessionSink, last_user_text
from coffer.infrastructure.chat.opencode_mapping import (
    OpencodeParseState,
    map_opencode_event,
)
from coffer.infrastructure.chat.opencode_run import (
    OpencodeSpawner,
    build_run_argv,
    default_spawn,
)
from coffer.infrastructure.chat.transcribe import (
    Transcriber,
    prompt_with_transcripts,
    transcribe_audio_attachments,
)

_logger = logging.getLogger(__name__)

#: Cap the stderr tail folded into a ``TurnError`` so a noisy failure can't blow
#: up the error message.
_STDERR_TAIL = 2000


class OpencodeRunAdapter:
    """One turn of an ``opencode run``-backed agent.

    The ``spawn`` seam lets tests inject a fake process with a canned stdout
    stream (no real ``opencode`` binary, no model call).
    """

    def __init__(
        self,
        *,
        cwd: str,
        resume_session: str | None,
        env: dict[str, str] | None = None,
        on_session: SessionSink,
        spawn: OpencodeSpawner | None = None,
        binary: str = "opencode",
        model: str | None = None,
        transcriber: Transcriber | None = None,
    ) -> None:
        self._cwd = cwd
        self._resume = resume_session
        self._env = env
        self._on_session = on_session
        self._spawn: OpencodeSpawner = spawn or default_spawn
        self._binary = binary
        self._transcriber = transcriber
        #: Optional (read by the orchestrator to stamp the assistant message).
        self.model_id: str | None = model

    async def run_turn(
        self,
        *,
        history: Sequence[Message],
        attachments: Sequence[Attachment] = (),
    ) -> AsyncIterator[AgentEvent]:
        # Match the platform's ``async def -> AsyncIterator`` seam: delegate to
        # ``_stream`` so the coroutine machinery runs at yield points.
        return self._stream(history, attachments)

    async def _persist_session(self, state: OpencodeParseState) -> None:
        """Write a newly-discovered session id back for the next ``--session``.

        Best-effort but logged (mirrors the Codex adapter): a failed write only
        costs session continuity, so it must not fail the turn.
        """
        if not state.session_id or state.session_id == self._resume:
            return
        try:
            await self._on_session(state.session_id)
        except Exception:
            _logger.warning(
                "opencode_agent.session_persist_failed",
                extra={"session_id": state.session_id},
                exc_info=True,
            )

    async def _stream(
        self, history: Sequence[Message], attachments: Sequence[Attachment] = ()
    ) -> AsyncIterator[AgentEvent]:
        # opencode's run mode takes a text message: transcribe voice to text and
        # hand other files as on-disk paths (path-native, like Codex).
        attachments, transcripts = await transcribe_audio_attachments(
            attachments, self._transcriber
        )
        prompt = prompt_with_transcripts(last_user_text(history), transcripts)
        if attachments:
            notes = "\n".join(
                f"[The user attached a file '{a.filename}', saved at {a.path}.]"
                for a in attachments
            )
            prompt = f"{prompt}\n\n{notes}".strip() if prompt else notes
        if not prompt:
            yield TurnError(code="empty_prompt", message="no user message to send")
            return

        state = OpencodeParseState(session_id=self._resume)
        argv = build_run_argv(prompt, resume_session=self._resume, binary=self._binary)
        yield TurnStarted()

        proc = await self._spawn(argv, self._cwd, self._env)
        try:
            assert proc.stdout is not None
            async for raw in proc.stdout:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue  # a non-JSON log line on stdout; skip it
                if isinstance(obj, dict):
                    for event in map_opencode_event(obj, state):
                        yield event
            code = await proc.wait()
            await self._persist_session(state)
            if not state.terminal_emitted:
                if code == 0:
                    yield TurnDone(
                        prompt_tokens=state.prompt_tokens,
                        completion_tokens=state.completion_tokens,
                        stop_reason="end_turn",
                    )
                else:
                    detail = await _read_stderr_tail(proc)
                    yield TurnError(
                        code="opencode_run_failed",
                        message=f"opencode run exited {code}: {detail}"[:_STDERR_TAIL],
                    )
                state.terminal_emitted = True
        except asyncio.CancelledError:
            with contextlib.suppress(ProcessLookupError, Exception):
                proc.kill()
            # The session id arrives early in the stream, so an interrupted turn
            # stays resumable.
            await self._persist_session(state)
            raise


async def _read_stderr_tail(proc: asyncio.subprocess.Process) -> str:
    """Best-effort tail of the process stderr for a failure message."""
    if proc.stderr is None:
        return ""
    try:
        data = await proc.stderr.read()
    except Exception:
        return ""
    return data.decode("utf-8", "replace").strip()[-500:]


__all__ = ["OpencodeRunAdapter"]
