"""ACP-backed hermes adapter — drive hermes via ``hermes acp``.

This adapter drives hermes through the Agent Client Protocol (ACP) — JSON-RPC 2.0
over stdio — reusing the generic
:class:`~coffer.infrastructure.chat.codex_jsonrpc.CodexRpcClient` NDJSON transport
(ACP and ``codex app-server`` share the same wire framing). It mirrors
``CodexAppServerAdapter`` structurally.

ACP differs from ``codex app-server`` in *where the turn terminal comes from*:
codex streams a ``turn/completed`` **notification**, whereas ACP's turn ends when
the ``session/prompt`` **request response** arrives (carrying ``stopReason``).
So ``_stream`` races the ``session/update`` notification stream against the
``session/prompt`` response future: it drains and maps every buffered update
first (notifications are always preferred over the terminal), then synthesises a
``TurnDone`` from the response's ``stopReason``. A terminal is always yielded
before the iterator ends (except on ``CancelledError``, which cleans up and
re-raises).

Approvals are handled client-side: hermes asks via a ``session/request_permission``
server→client request, and this adapter auto-allows (parity with Codex's
``approvalPolicy=never``) — Coffer drives the agent, so the owner is the trust
boundary.

Only stdlib ``asyncio`` + ``json`` are used (via ``CodexRpcClient``); no
third-party dependency (the ``acp`` python package is hermes-side only).
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
from coffer.infrastructure.chat.codex_jsonrpc import CodexRpcClient
from coffer.infrastructure.chat.hermes_acp import AcpSessionFactory, HermesAcpSession
from coffer.infrastructure.chat.hermes_mapping import HermesParseState, map_hermes_update
from coffer.infrastructure.chat.transcribe import (
    Transcriber,
    prompt_with_transcripts,
    transcribe_audio_attachments,
)

_logger = logging.getLogger(__name__)

#: ACP protocol version Coffer speaks. Coffer declines the client filesystem
#: capabilities (it does not proxy file reads/writes for the agent — hermes runs
#: with real disk access in its cwd).
_INITIALIZE_PARAMS: dict[str, Any] = {
    "protocolVersion": 1,
    "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}},
}

#: Permission-option kinds that grant the request, most-preferred first.
_ALLOW_KINDS = ("allow_always", "allow_once")


class HermesAcpAdapter:
    """One turn of an ACP-backed hermes agent.

    Mirrors ``CodexAppServerAdapter``: an injected ``session_factory`` seam, a
    ``run_turn`` that returns ``self._stream(...)``, best-effort logged session-id
    persistence, and ``CancelledError`` cleanup that cancels the turn + closes
    (kills + reaps) the session and still persists the session id.
    """

    def __init__(
        self,
        *,
        cwd: str,
        resume_session: str | None,
        extra: dict[str, Any],
        session_factory: AcpSessionFactory,
        on_session: SessionSink,
        env: dict[str, str] | None = None,
        transcriber: Transcriber | None = None,
    ) -> None:
        self._cwd = cwd
        self._resume = resume_session
        self._extra = extra
        self._session_factory = session_factory
        self._on_session = on_session
        self._env = env
        self._transcriber = transcriber
        model = extra.get("model")
        if isinstance(model, str) and model:
            #: Names the model the turn ran on; the orchestrator records it on the
            #: assistant message (optional per the AgentAdapter port).
            self.model_id: str = model

    async def run_turn(
        self,
        *,
        history: Sequence[Message],
        attachments: Sequence[Attachment] = (),
    ) -> AsyncIterator[AgentEvent]:
        # Delegate to ``_stream`` so the coroutine machinery runs at yield points
        # rather than at the ``await run_turn(...)`` call site (mirrors the codex
        # and SDK adapters).
        return self._stream(history, attachments)

    async def _persist_session(self, state: HermesParseState) -> None:
        """Write a newly-discovered session id back for the next ``session/load``.

        Best-effort but logged: a failed write only costs session continuity, so
        it must not fail the turn.
        """
        if not state.session_id or state.session_id == self._resume:
            return
        try:
            await self._on_session(state.session_id)
        except Exception:
            _logger.warning(
                "hermes_agent.session_persist_failed",
                extra={"session_id": state.session_id},
                exc_info=True,
            )

    @staticmethod
    def _pick_allow_option(params: dict[str, Any]) -> str | None:
        """The ``optionId`` to auto-select for a ``session/request_permission``.

        Prefer an explicit allow option (``allow_always`` then ``allow_once``);
        fall back to the first option offered. Returns ``None`` only when no
        option carries an ``optionId``.
        """
        options = params.get("options")
        if not isinstance(options, list):
            return None
        by_kind: dict[str, str] = {}
        first: str | None = None
        for opt in options:
            if not isinstance(opt, dict):
                continue
            opt_id = opt.get("optionId")
            if not isinstance(opt_id, str) or not opt_id:
                continue
            if first is None:
                first = opt_id
            kind = opt.get("kind")
            if isinstance(kind, str) and kind not in by_kind:
                by_kind[kind] = opt_id
        for kind in _ALLOW_KINDS:
            if kind in by_kind:
                return by_kind[kind]
        return first

    async def _open_session(self, rpc: CodexRpcClient) -> str:
        """Run ``initialize`` then ``session/new`` | ``session/load``.

        Returns the ACP session id: for a new session the one the agent minted;
        for a resumed session the id we asked it to load.
        """
        await rpc.request("initialize", _INITIALIZE_PARAMS)
        if self._resume:
            await rpc.request(
                "session/load",
                {"sessionId": self._resume, "cwd": self._cwd, "mcpServers": []},
            )
            return self._resume
        result = await rpc.request("session/new", {"cwd": self._cwd, "mcpServers": []})
        session_id = result.get("sessionId")
        return session_id if isinstance(session_id, str) and session_id else ""

    async def _stream(
        self, history: Sequence[Message], attachments: Sequence[Attachment] = ()
    ) -> AsyncIterator[AgentEvent]:
        # hermes cannot hear audio: transcribe voice to text; keep other files.
        attachments, transcripts = await transcribe_audio_attachments(
            attachments, self._transcriber
        )
        prompt = prompt_with_transcripts(last_user_text(history), transcripts)
        if attachments:
            # hermes is path-native (no inline media over ACP text prompts): hand
            # it the on-disk paths so it can open them with its own tools.
            notes = "\n".join(
                f"[The user attached a file '{a.filename}', saved at {a.path}.]"
                for a in attachments
            )
            prompt = f"{prompt}\n\n{notes}".strip() if prompt else notes
        if not prompt:
            yield TurnError(code="empty_prompt", message="no user message to send")
            return

        state = HermesParseState(session_id=self._resume)
        yield TurnStarted()

        session: HermesAcpSession = self._session_factory(self._cwd, self._env)
        await session.start()
        rpc = session.rpc

        async def _auto_allow(params: dict[str, Any]) -> dict[str, Any]:
            option_id = self._pick_allow_option(params)
            if option_id is None:
                return {"outcome": {"outcome": "cancelled"}}
            return {"outcome": {"outcome": "selected", "optionId": option_id}}

        rpc.on_request("session/request_permission", _auto_allow)

        prompt_task: asyncio.Task[dict[str, Any]] | None = None
        next_task: asyncio.Future[Any] | None = None
        eof_waiter: asyncio.Future[Any] = asyncio.ensure_future(rpc.eof.wait())
        try:
            session_id = await self._open_session(rpc)
            if session_id:
                state.session_id = session_id
            await self._persist_session(state)

            notifications = rpc.notifications()
            # Start the prompt request; its response is the turn terminal. The
            # ``session/update`` notifications for this turn arrive on the stream
            # BEFORE the response resolves, so racing the two and preferring the
            # notification drains every buffered update before terminating.
            prompt_task = asyncio.create_task(
                rpc.request(
                    "session/prompt",
                    {
                        "sessionId": state.session_id or session_id,
                        "prompt": [{"type": "text", "text": prompt}],
                    },
                )
            )
            while True:
                if next_task is None:
                    next_task = asyncio.ensure_future(notifications.__anext__())
                await asyncio.wait(
                    {next_task, prompt_task, eof_waiter},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if next_task.done():
                    method, params = next_task.result()
                    next_task = None
                    if method == "session/update":
                        for event in map_hermes_update(params, state):
                            yield event
                    continue
                # No notification is pending — the prompt resolved (or the stream
                # reached EOF). Stop draining and synthesise the terminal.
                break

            result = await prompt_task  # raises if the RPC stream ended first
            stop = result.get("stopReason") if isinstance(result, dict) else None
            state.terminal_emitted = True
            yield TurnDone(
                prompt_tokens=None,
                completion_tokens=None,
                stop_reason=stop if isinstance(stop, str) and stop else "end_turn",
            )
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                if state.session_id:
                    await rpc.notify("session/cancel", {"sessionId": state.session_id})
            # Persist the session id even on interruption: it is captured early
            # (the session/new response), so an interrupted turn stays resumable.
            await self._persist_session(state)
            raise
        except Exception as exc:  # surface any RPC/stream failure as a terminal
            if not state.terminal_emitted:
                yield TurnError(code="hermes_error", message=str(exc))
        finally:
            for fut in (next_task, prompt_task, eof_waiter):
                if fut is not None and not fut.done():
                    fut.cancel()
                    with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration, Exception):
                        await fut
            with contextlib.suppress(Exception):
                await session.close()


__all__ = ["HermesAcpAdapter"]
