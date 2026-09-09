"""SDK-backed Claude adapter — drive Claude Code via ``claude-agent-sdk``.

This adapter drives Claude Code through the Python ``ClaudeSDKClient`` rather
than shelling out to ``claude -p``. The agent runs with full
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
import base64
import contextlib
import logging
import pathlib
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any, Protocol

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
)

from coffer.domain.chat.attachment import Attachment
from coffer.domain.chat.events import (
    AgentEvent,
    TurnDone,
    TurnError,
    TurnStarted,
)
from coffer.domain.chat.message import Message
from coffer.infrastructure.chat.adapter_support import ParseState, SessionSink, last_user_text
from coffer.infrastructure.chat.claude_sdk_mapping import map_sdk_message
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


# ---------------------------------------------------------------------------
# Session injection seam
# ---------------------------------------------------------------------------


class ClaudeSdkSession(Protocol):
    """The thin slice of ``ClaudeSDKClient`` the adapter drives, behind a seam.

    Injected via :data:`SdkSessionFactory` so turns can be tested with a fake
    session that replays canned SDK messages — no real ``claude`` binary needed.
    """

    async def connect(self, prompt: str | list[dict[str, Any]]) -> None: ...

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

    async def connect(self, prompt: str | list[dict[str, Any]]) -> None:
        # Pass the single user turn as a one-message async stream rather than a
        # plain string (the SDK streams it, waits for the result, then ends
        # input). ``prompt`` is either the plain text or, when the turn carries
        # attachments, a list of content blocks (text + base64 image/document) —
        # both are valid ``content`` shapes for the stream-json user frame.
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


#: Image mime types the Messages API accepts as an inline ``image`` block. An
#: image in any other format (e.g. a HEIC/bmp/tiff/svg sent as a document) would
#: 400 the whole turn, so it falls through to the on-disk path pointer instead.
_INLINE_IMAGE_MIMES = frozenset({"image/jpeg", "image/png", "image/gif", "image/webp"})


def _attachment_block(att: Attachment) -> dict[str, Any]:
    """Materialise one attachment into a stream-json content block.

    A supported image becomes a native base64 ``image`` block Claude sees directly;
    the base64 lives only in this outbound request, never the DB. Documents are
    text-extracted upstream (FR-030) and never reach here, so anything else (audio,
    a document whose extraction failed, an odd image format, …) becomes a text
    pointer to the on-disk path so the agent can open it with its own tools. An
    unreadable file degrades to a text note rather than failing the turn.
    """
    try:
        data = pathlib.Path(att.path).read_bytes()
    except OSError:
        return {"type": "text", "text": f"[Attached file '{att.filename}' could not be read]"}
    if att.mime in _INLINE_IMAGE_MIMES:
        encoded = base64.standard_b64encode(data).decode()
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": att.mime, "data": encoded},
        }
    return {
        "type": "text",
        "text": (
            f"[The user attached a file '{att.filename}', saved at {att.path}. "
            "Open it with your tools if it is relevant.]"
        ),
    }


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

    Has an injected ``session_factory`` seam, a
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
        system_context: str | None = None,
        transcriber: Transcriber | None = None,
        document_extractor: DocumentExtractor | None = None,
    ) -> None:
        self._cwd = cwd
        self._resume = resume_session
        self._extra = extra
        self._session_factory = session_factory
        self._on_session = on_session
        self._env = env
        self._system_context = system_context
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
        # at the ``await run_turn(...)`` call site (the codex adapter does the same).
        return self._stream(history, attachments)

    async def _persist_session(self, state: ParseState) -> None:
        """Write a newly-discovered SDK session id back for the next ``resume``.

        Best-effort but logged: a failed write only costs
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
        if self._system_context:
            # Tell a channel-driven agent it is bridged to a chat (be concise,
            # no clickable dialogs) by appending to Claude Code's own preset
            # prompt rather than replacing it.
            opts.system_prompt = {
                "type": "preset",
                "preset": "claude_code",
                "append": self._system_context,
            }
        return opts

    @staticmethod
    def _build_content(
        prompt: str, attachments: Sequence[Attachment]
    ) -> str | list[dict[str, Any]]:
        """The turn's user content: the plain prompt when there are no
        attachments (unchanged behaviour), else a block list of the text plus
        each materialised attachment."""
        if not attachments:
            return prompt
        blocks: list[dict[str, Any]] = []
        if prompt:
            blocks.append({"type": "text", "text": prompt})
        blocks.extend(_attachment_block(att) for att in attachments)
        return blocks

    async def _connect(
        self, prompt: str | list[dict[str, Any]], *, resume: str | None
    ) -> ClaudeSdkSession:
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

    async def _stream(
        self, history: Sequence[Message], attachments: Sequence[Attachment] = ()
    ) -> AsyncIterator[AgentEvent]:
        # Claude cannot hear audio: transcribe any voice attachment to text and
        # fold it into the prompt. A document (PDF/office file) is text-extracted
        # and folded in too (FR-030) so it goes as text, not a vision/binary block;
        # the rest are materialised as content blocks.
        attachments, transcripts = await transcribe_audio_attachments(
            attachments, self._transcriber
        )
        attachments, extracts = await extract_document_attachments(
            attachments, self._document_extractor
        )
        prompt = prompt_with_transcripts(last_user_text(history), transcripts)
        prompt = prompt_with_document_text(prompt, extracts)
        content = self._build_content(prompt, attachments)
        if not content:
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
            session = await self._connect(content, resume=self._resume)
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
                session = await self._connect(content, resume=None)
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
