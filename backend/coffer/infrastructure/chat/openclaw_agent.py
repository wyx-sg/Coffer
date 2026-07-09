"""``openclaw agent``-backed adapter — one NON-STREAMING turn per subprocess.

Structurally the simplest adapter: openclaw's headless turn (``openclaw agent
--json --local``) prints ONE JSON blob on stdout when the turn completes, so
there is no event stream to parse — the adapter spawns the process, reads
stdout to EOF, and synthesises ``TurnStarted`` → one ``TextDelta`` →
``TurnDone`` from the parsed blob (:func:`map_openclaw_result`). The upstream
session is pinned by the ``--session-key`` Coffer derives from the conversation
id, so nothing is discovered from the output and there is no ``on_session``
persistence.

stderr is drained CONCURRENTLY (a background task, like the other subprocess
adapters): openclaw logs verbosely to stderr, and reading stdout while leaving
stderr to fill its OS pipe would deadlock the subprocess. Only stdlib
``asyncio`` + ``json`` are used.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator, Sequence

from coffer.domain.chat.attachment import Attachment
from coffer.domain.chat.events import AgentEvent, TextDelta, TurnDone, TurnError, TurnStarted
from coffer.domain.chat.message import Message
from coffer.infrastructure.chat.adapter_support import last_user_text
from coffer.infrastructure.chat.document_extract import (
    DocumentExtractor,
    extract_document_attachments,
    prompt_with_document_text,
)
from coffer.infrastructure.chat.openclaw_mapping import map_openclaw_result
from coffer.infrastructure.chat.openclaw_run import (
    OpenclawSpawner,
    build_agent_argv,
    default_spawn,
)
from coffer.infrastructure.chat.transcribe import (
    Transcriber,
    prompt_with_transcripts,
    transcribe_audio_attachments,
)

_logger = logging.getLogger(__name__)

#: Keep at most this many trailing stderr lines for a failure message (bounded
#: memory — openclaw's stderr logging can be large over a long turn).
_STDERR_TAIL_LINES = 100
#: Cap the folded stderr tail length in a ``TurnError`` message.
_STDERR_TAIL_CHARS = 2000


class OpenclawAgentAdapter:
    """One turn of an ``openclaw agent``-backed agent.

    The ``spawn`` seam lets tests inject a fake process with a canned stdout
    blob (no real ``openclaw`` binary, no model call).
    """

    def __init__(
        self,
        *,
        cwd: str,
        session_key: str,
        env: dict[str, str] | None = None,
        spawn: OpenclawSpawner | None = None,
        binary: str = "openclaw",
        model: str | None = None,
        transcriber: Transcriber | None = None,
        document_extractor: DocumentExtractor | None = None,
    ) -> None:
        # The PROCESS working directory only — openclaw has no cwd flag and runs
        # every turn in its own agent workspace (see openclaw_provider).
        self._cwd = cwd
        self._session_key = session_key
        self._env = env
        self._spawn: OpenclawSpawner = spawn or default_spawn
        self._binary = binary
        self._model = model
        self._transcriber = transcriber
        self._document_extractor = document_extractor
        #: Read by the orchestrator to stamp the assistant message. Starts as
        #: the conversation's override and is refined to the execution trace's
        #: winner once the blob is parsed.
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

    async def _stream(
        self, history: Sequence[Message], attachments: Sequence[Attachment] = ()
    ) -> AsyncIterator[AgentEvent]:
        # openclaw's turn takes a text message: transcribe voice to text,
        # extract documents to text (FR-030 — the message is text-only), and
        # hand other files as on-disk paths (like the other CLI adapters).
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

        argv = build_agent_argv(
            prompt, session_key=self._session_key, model=self._model, binary=self._binary
        )
        yield TurnStarted()

        proc = await self._spawn(argv, self._cwd, self._env)
        stderr_tail: list[bytes] = []
        stderr_task: asyncio.Task[None] | None = None
        if proc.stderr is not None:
            stderr_task = asyncio.create_task(_drain_stderr(proc.stderr, stderr_tail))
        try:
            assert proc.stdout is not None
            # NON-STREAMING: the blob arrives whole when the turn completes, so
            # read stdout to EOF (no line framing, no reader-limit concerns).
            raw = await proc.stdout.read()
            code = await proc.wait()
            if code != 0:
                # Let the drain reach EOF (the process has exited, so it is
                # imminent) so the failure message carries the actual tail.
                if stderr_task is not None:
                    with contextlib.suppress(Exception, asyncio.TimeoutError):
                        await asyncio.wait_for(asyncio.shield(stderr_task), timeout=2)
                detail = _join_tail(stderr_tail)
                yield TurnError(
                    code="openclaw_run_failed",
                    message=f"openclaw agent exited {code}: {detail}"[:_STDERR_TAIL_CHARS],
                )
                return
            try:
                blob = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                yield TurnError(
                    code="openclaw_parse_failed",
                    message="openclaw agent printed no parseable JSON result",
                )
                return
            if not isinstance(blob, dict):
                yield TurnError(
                    code="openclaw_parse_failed",
                    message="openclaw agent result is not a JSON object",
                )
                return
            turn = map_openclaw_result(blob)
            if turn.model_id:
                self.model_id = turn.model_id
            if turn.text:
                # One delta — the whole reply (there is no incremental stream).
                yield TextDelta(text=turn.text)
            yield TurnDone(
                prompt_tokens=None,
                completion_tokens=None,
                stop_reason=turn.stop_reason,
            )
        except asyncio.CancelledError:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            with contextlib.suppress(Exception):
                await proc.wait()  # reap so no zombie lingers
            # The session key is Coffer-derived, so an interrupted turn stays
            # resumable with no persistence needed.
            raise
        finally:
            if stderr_task is not None:
                stderr_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await stderr_task


async def _drain_stderr(stream: asyncio.StreamReader, sink: list[bytes]) -> None:
    """Concurrently drain the subprocess stderr into a bounded tail buffer.

    Keeps the stderr pipe empty so the subprocess never blocks on ``write``
    (the deadlock the other subprocess adapters also guard against). Retains
    only the last ``_STDERR_TAIL_LINES`` lines for a possible failure message.
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


__all__ = ["OpenclawAgentAdapter"]
