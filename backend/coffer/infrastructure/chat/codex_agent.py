"""App-server-backed Codex adapter — drive Codex via ``codex app-server``.

This adapter drives Codex through the bidirectional ``codex app-server`` JSON-RPC
protocol (NDJSON over stdio) rather than shelling out to ``codex exec --json``.
Codex runs with full permissions (``never`` ask,
``danger-full-access``): Coffer does not gate individual tool calls — the owner
driving the conversation is the trust boundary.

This mirrors ``ClaudeSdkAgentAdapter`` structurally: a single ``asyncio.Queue``
fed by a ``pump()`` task (streamed notifications); ``_stream`` drains the queue
and yields the platform's ``AgentEvent``s.

Only stdlib ``asyncio`` + ``json`` are used (via ``CodexRpcClient``); the
``codex_agent`` module imports no third-party dependency (Contract 9).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any

from coffer.domain.chat.attachment import Attachment
from coffer.domain.chat.events import (
    AgentEvent,
    TurnDone,
    TurnError,
    TurnStarted,
)
from coffer.domain.chat.message import Message
from coffer.infrastructure.chat.adapter_support import SessionSink, last_user_text
from coffer.infrastructure.chat.codex_app_server import (
    AppServerSessionFactory,
    CodexAppServerSession,
)
from coffer.infrastructure.chat.codex_jsonrpc import CodexRpcClient
from coffer.infrastructure.chat.codex_mapping import (
    CodexParseState,
    map_codex_notification,
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

#: Sentinel pushed after the terminal event so ``_stream`` knows to stop.
_SENTINEL = object()

#: JSON-RPC client info Coffer announces in the ``initialize`` handshake.
_CLIENT_INFO = {"name": "coffer", "title": None, "version": "0"}


class CodexAppServerAdapter:
    """One turn of an app-server-backed Codex agent.

    Mirrors ``ClaudeSdkAgentAdapter``: an injected ``session_factory`` seam, a
    ``run_turn`` that returns ``self._stream(...)``, best-effort logged session
    (thread id) persistence, and ``CancelledError`` cleanup that interrupts the
    turn + closes the session and still persists the thread id.
    """

    def __init__(
        self,
        *,
        cwd: str,
        resume_session: str | None,
        extra: dict[str, Any],
        session_factory: AppServerSessionFactory,
        on_session: SessionSink,
        env: dict[str, str] | None = None,
        transcriber: Transcriber | None = None,
        document_extractor: DocumentExtractor | None = None,
    ) -> None:
        self._cwd = cwd
        self._resume = resume_session
        self._extra = extra
        self._session_factory = session_factory
        self._on_session = on_session
        self._env = env
        self._transcriber = transcriber
        self._document_extractor = document_extractor

    async def run_turn(
        self,
        *,
        history: Sequence[Message],
        attachments: Sequence[Attachment] = (),
    ) -> AsyncIterator[AgentEvent]:
        # Match the platform's ``async def -> AsyncIterator`` seam: delegate to
        # ``_stream`` so the coroutine machinery runs at yield points rather than
        # at the ``await run_turn(...)`` call site (the SDK adapter does the same).
        return self._stream(history, attachments)

    async def _persist_session(self, state: CodexParseState) -> None:
        """Write a newly-discovered thread id back for the next ``resume``.

        Best-effort but logged (mirrors the SDK adapter): a failed write only
        costs session continuity, so it must not fail the turn.
        """
        if not state.session_id or state.session_id == self._resume:
            return
        try:
            await self._on_session(state.session_id)
        except Exception:
            _logger.warning(
                "codex_agent.session_persist_failed",
                extra={"session_id": state.session_id},
                exc_info=True,
            )

    async def _drive_handshake(self, rpc: CodexRpcClient, prompt: str) -> str:
        """Run initialize → initialized → thread/start|resume → turn/start.

        Returns the turn id (needed to interrupt). The thread id lands in the
        parse state via the ``thread/started`` notification the pump maps.
        """
        await rpc.request("initialize", {"clientInfo": _CLIENT_INFO, "capabilities": None})
        await rpc.notify("initialized")

        model = self._extra.get("model")
        # Full permissions — Coffer does not gate individual tool calls; the owner
        # driving the conversation is the trust boundary.
        if self._resume:
            thread_params: dict[str, Any] = {
                "threadId": self._resume,
                "cwd": self._cwd,
                "approvalPolicy": "never",
                "sandbox": "danger-full-access",
            }
            if model:
                thread_params["model"] = model
            thread = await rpc.request("thread/resume", thread_params)
        else:
            thread_params = {
                "cwd": self._cwd,
                "approvalPolicy": "never",
                "sandbox": "danger-full-access",
            }
            if model:
                thread_params["model"] = model
            thread = await rpc.request("thread/start", thread_params)
        thread_id = (thread.get("thread") or {}).get("id") or self._resume or ""

        turn = await rpc.request(
            "turn/start",
            {
                "threadId": thread_id,
                "input": [{"type": "text", "text": prompt, "text_elements": []}],
            },
        )
        return (turn.get("turn") or {}).get("id") or ""

    async def _stream(
        self, history: Sequence[Message], attachments: Sequence[Attachment] = ()
    ) -> AsyncIterator[AgentEvent]:
        # Codex cannot hear audio: transcribe voice to text; extract documents to
        # text (FR-030 — Codex is path-native and cannot parse a binary PDF); keep
        # other files as path notes.
        attachments, transcripts = await transcribe_audio_attachments(
            attachments, self._transcriber
        )
        attachments, extracts = await extract_document_attachments(
            attachments, self._document_extractor
        )
        prompt = prompt_with_transcripts(last_user_text(history), transcripts)
        prompt = prompt_with_document_text(prompt, extracts)
        if attachments:
            # Codex is path-native (no inline image blocks over its app-server
            # RPC): hand it the on-disk paths so it can open them with its tools.
            notes = "\n".join(
                f"[The user attached a file '{a.filename}', saved at {a.path}.]"
                for a in attachments
            )
            prompt = f"{prompt}\n\n{notes}".strip() if prompt else notes
        if not prompt:
            yield TurnError(code="empty_prompt", message="no user message to send")
            return

        state = CodexParseState(session_id=self._resume)
        queue: asyncio.Queue[Any] = asyncio.Queue()
        yield TurnStarted()

        session: CodexAppServerSession = self._session_factory(self._cwd, self._env)
        await session.start()
        rpc = session.rpc

        async def pump() -> None:
            # Map streamed notifications onto the queue. A sentinel after the
            # terminal event ends the drain. The iterator ends when the RPC
            # stream reaches EOF so a turn that never sends ``turn/completed``
            # still terminates (the ``_stream`` tail then synthesizes a
            # ``TurnDone``).
            try:
                async for method, params in _notifications_until_eof(rpc):
                    for event in map_codex_notification(method, params, state):
                        await queue.put(event)
                        if isinstance(event, (TurnDone, TurnError)):
                            await queue.put(_SENTINEL)
                            return
                await queue.put(_SENTINEL)  # stream ended without a terminal
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # surface pump failures as a terminal error
                state.terminal_emitted = True
                await queue.put(TurnError(code="codex_stream_error", message=str(exc)))
                await queue.put(_SENTINEL)

        pump_task: asyncio.Task[None] | None = None
        turn_id = ""
        try:
            # Start the pump BEFORE the handshake so notifications emitted in
            # response to thread/start or turn/start are never missed: the read
            # loop is already running (session.start spun it up), but the pump is
            # the only consumer of ``rpc.notifications()`` — start it first so it
            # is draining before any notification can be produced.
            pump_task = asyncio.create_task(pump())
            turn_id = await self._drive_handshake(rpc, prompt)
            while True:
                item = await queue.get()
                if item is _SENTINEL:
                    break
                yield item
            await self._persist_session(state)
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                if turn_id and state.session_id:
                    await rpc.request(
                        "turn/interrupt",
                        {"threadId": state.session_id, "turnId": turn_id},
                    )
            # Persist the thread id even on interruption: it arrives early (the
            # thread/started notification), so an interrupted turn stays resumable.
            await self._persist_session(state)
            raise
        finally:
            if pump_task is not None:
                pump_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await pump_task
            with contextlib.suppress(Exception):
                await session.close()

        if not state.terminal_emitted:
            # The stream ended without a turn/completed — synthesize a terminal
            # so the orchestrator never hangs waiting for one.
            yield TurnDone(
                prompt_tokens=state.prompt_tokens,
                completion_tokens=state.completion_tokens,
                stop_reason="end_turn",
            )


async def _notifications_until_eof(
    rpc: CodexRpcClient,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """Yield notifications until the RPC read loop reaches EOF.

    Race each fetch against the public ``rpc.eof`` signal; when the read loop
    has finished AND no buffered notification remains, end cleanly so ``_stream``
    can synthesize a terminal.  The ``finally`` block always cancels in-flight
    futures to prevent "Task was destroyed but it is pending!" warnings when the
    pump task is cancelled mid-wait.
    """
    stream = rpc.notifications()
    eof_waiter: asyncio.Future[Any] = asyncio.ensure_future(rpc.eof.wait())
    nxt: asyncio.Future[Any] | None = None
    try:
        while True:
            nxt = asyncio.ensure_future(stream.__anext__())
            await asyncio.wait({nxt, eof_waiter}, return_when=asyncio.FIRST_COMPLETED)
            if nxt.done():
                yield nxt.result()
                nxt = None
                continue
            # EOF fired first — give any notification produced in the same tick
            # a chance to land, then stop if none did.
            await asyncio.sleep(0)
            if nxt.done():
                yield nxt.result()
                nxt = None
                continue
            return  # EOF and no buffered notification
    finally:
        if not eof_waiter.done():
            eof_waiter.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await eof_waiter
        if nxt is not None and not nxt.done():
            nxt.cancel()
            with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration, Exception):
                await nxt


__all__ = ["CodexAppServerAdapter"]
