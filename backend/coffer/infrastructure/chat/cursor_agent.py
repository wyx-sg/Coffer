"""``cursor-agent``-backed adapter — one ``AgentAdapter`` turn per subprocess.

Structurally identical to :class:`OpencodeRunAdapter`: cursor-agent's headless
print mode is a per-turn subprocess (``cursor-agent -p --output-format
stream-json``) whose stdout is line-delimited JSON (NDJSON), so there is no
persistent app-server or JSON-RPC session to manage. The adapter spawns the
process, maps each stdout line via :func:`map_cursor_event`, and synthesises the
terminal ``TurnDone`` / ``TurnError`` on process exit (a ``TurnDone`` on a clean
exit with the ``result`` marker's ``is_error`` false; a ``TurnError`` otherwise).
The upstream chat id (for ``--resume``) is discovered from the ``system`` init
event and persisted via ``on_session``.

stderr is drained CONCURRENTLY (a background task, like the Codex app-server and
opencode adapters): reading stdout while leaving stderr to fill its OS pipe would
deadlock the subprocess. Only stdlib ``asyncio`` + ``json`` are used.

.. note::
   cursor-agent is locked to Cursor's own backend and its own auth
   (``cursor-agent login`` / ``CURSOR_API_KEY``); Coffer projects NO connection
   and injects NO key, so the adapter inherits the daemon env unchanged. A live
   run could not be exercised in the build sandbox — see :mod:`cursor_run`.
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
from coffer.infrastructure.chat.cursor_mapping import CursorParseState, map_cursor_event
from coffer.infrastructure.chat.cursor_run import (
    CursorSpawner,
    build_run_argv,
    default_spawn,
)
from coffer.infrastructure.chat.document_extract import (
    DocumentExtractor,
    extract_document_attachments,
    prompt_with_document_text,
)
from coffer.infrastructure.chat.transcribe import (
    Transcriber,
    prompt_with_transcripts,
    transcribe_audio_attachments,
)

_logger = logging.getLogger(__name__)

#: Keep at most this many trailing stderr lines for a failure message (bounded
#: memory — cursor-agent's stderr can be large over a long turn).
_STDERR_TAIL_LINES = 100
#: Cap the folded stderr tail length in a ``TurnError`` message.
_STDERR_TAIL_CHARS = 2000


class CursorRunAdapter:
    """One turn of a ``cursor-agent``-backed agent.

    The ``spawn`` seam lets tests inject a fake process with a canned stdout
    stream (no real ``cursor-agent`` binary, no Cursor-backend call).
    """

    def __init__(
        self,
        *,
        cwd: str,
        resume_session: str | None,
        env: dict[str, str] | None = None,
        on_session: SessionSink,
        spawn: CursorSpawner | None = None,
        binary: str = "cursor-agent",
        transcriber: Transcriber | None = None,
        document_extractor: DocumentExtractor | None = None,
    ) -> None:
        self._cwd = cwd
        self._resume = resume_session
        # Cursor uses its OWN auth (`cursor-agent login` / CURSOR_API_KEY); Coffer
        # projects no connection and injects no key, so ``env`` is normally None
        # (inherit the daemon env unchanged).
        self._env = env
        self._on_session = on_session
        self._spawn: CursorSpawner = spawn or default_spawn
        self._binary = binary
        self._transcriber = transcriber
        self._document_extractor = document_extractor

    async def run_turn(
        self,
        *,
        history: Sequence[Message],
        attachments: Sequence[Attachment] = (),
    ) -> AsyncIterator[AgentEvent]:
        # Match the platform's ``async def -> AsyncIterator`` seam: delegate to
        # ``_stream`` so the coroutine machinery runs at yield points.
        return self._stream(history, attachments)

    async def _persist_session(self, state: CursorParseState) -> None:
        """Write a newly-discovered chat id back for the next ``--resume``.

        Best-effort but logged (mirrors the opencode adapter): a failed write only
        costs session continuity, so it must not fail the turn.
        """
        if not state.session_id or state.session_id == self._resume:
            return
        try:
            await self._on_session(state.session_id)
        except Exception:
            _logger.warning(
                "cursor_agent.session_persist_failed",
                extra={"session_id": state.session_id},
                exc_info=True,
            )

    async def _stream(
        self, history: Sequence[Message], attachments: Sequence[Attachment] = ()
    ) -> AsyncIterator[AgentEvent]:
        # cursor-agent's print mode takes a text prompt: transcribe voice to text,
        # extract documents to text (FR-030 — path-native, cannot parse a binary
        # PDF), and hand other files as on-disk paths (like opencode).
        attachments, transcripts = await transcribe_audio_attachments(
            attachments, self._transcriber
        )
        attachments, extracts = await extract_document_attachments(
            attachments, self._document_extractor
        )
        prompt = prompt_with_transcripts(last_user_text(history), transcripts)
        prompt = prompt_with_document_text(prompt, extracts)
        if attachments:
            notes = "\n".join(
                f"[The user attached a file '{a.filename}', saved at {a.path}.]"
                for a in attachments
            )
            prompt = f"{prompt}\n\n{notes}".strip() if prompt else notes
        if not prompt:
            yield TurnError(code="empty_prompt", message="no user message to send")
            return

        state = CursorParseState(session_id=self._resume)
        argv = build_run_argv(prompt, resume_session=self._resume, binary=self._binary)
        yield TurnStarted()

        proc = await self._spawn(argv, self._cwd, self._env)
        stderr_tail: list[bytes] = []
        stderr_task: asyncio.Task[None] | None = None
        if proc.stderr is not None:
            stderr_task = asyncio.create_task(_drain_stderr(proc.stderr, stderr_tail))
        try:
            assert proc.stdout is not None
            while True:
                try:
                    raw = await proc.stdout.readline()
                except (ValueError, asyncio.LimitOverrunError):
                    # One JSON line exceeded the reader limit; readline() drops it
                    # from the buffer, so skip it and keep reading the next line.
                    continue
                if not raw:
                    break  # EOF
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue  # a non-JSON log line on stdout; skip it
                if isinstance(obj, dict):
                    for event in map_cursor_event(obj, state):
                        yield event
            code = await proc.wait()
            await self._persist_session(state)
            if not state.terminal_emitted:
                if code == 0 and not state.is_error:
                    yield TurnDone(
                        prompt_tokens=None,
                        completion_tokens=None,
                        stop_reason="end_turn",
                    )
                else:
                    detail = _join_tail(stderr_tail)
                    yield TurnError(
                        code="cursor_run_failed",
                        message=(
                            f"cursor-agent exited {code} (is_error={state.is_error}): {detail}"
                        )[:_STDERR_TAIL_CHARS],
                    )
                state.terminal_emitted = True
        except asyncio.CancelledError:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            with contextlib.suppress(Exception):
                await proc.wait()  # reap so no zombie lingers
            # The chat id arrives early in the stream, so an interrupted turn stays
            # resumable.
            await self._persist_session(state)
            raise
        finally:
            if stderr_task is not None:
                stderr_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await stderr_task


async def _drain_stderr(stream: asyncio.StreamReader, sink: list[bytes]) -> None:
    """Concurrently drain the subprocess stderr into a bounded tail buffer.

    Keeps the stderr pipe empty so the subprocess never blocks on ``write`` (the
    deadlock the opencode + Codex adapters also guard against). Retains only the
    last ``_STDERR_TAIL_LINES`` lines for a possible failure message.
    """
    while True:
        try:
            chunk = await stream.readline()
        except (ValueError, asyncio.LimitOverrunError):
            continue  # an over-long stderr line; keep draining
        if not chunk:
            return  # EOF
        sink.append(chunk)
        if len(sink) > _STDERR_TAIL_LINES:
            del sink[0]


def _join_tail(sink: list[bytes]) -> str:
    return b"".join(sink).decode("utf-8", "replace").strip()[-500:]


__all__ = ["CursorRunAdapter"]
