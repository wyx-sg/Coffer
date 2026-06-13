"""App-server-backed Codex adapter — drive Codex via ``codex app-server`` and
relay per-tool approvals through Coffer's approval seam (spec 008, T4/T5/T9).

Where the legacy ``CodexDialect`` shelled out to ``codex exec --json`` and could
only stream output (no approval bridging), this adapter drives Codex through the
bidirectional ``codex app-server`` JSON-RPC protocol (NDJSON over stdio). The
server→client ``item/.../requestApproval`` requests are the relay point: when
Codex wants to run a shell command or apply a file change it asks for approval,
the adapter emits an ``ApprovalRequest`` event and ``await``s the human decision
on the ``ApprovalGate``, then answers Codex with ``{"decision": "accept"}`` /
``{"decision": "decline"}``.

This mirrors ``ClaudeSdkAgentAdapter`` structurally: a single ``asyncio.Queue``
fed by a ``pump()`` task (streamed notifications) AND the approval handlers, so
events interleave in arrival order; ``_stream`` drains the queue and yields the
platform's ``AgentEvent``s. Because ``CodexRpcClient`` dispatches each
server→client request in its OWN task, ``await``ing the human decision inside a
handler blocks only that task — the pump keeps draining and ``_stream`` keeps
yielding, so the orchestrator sees the ``ApprovalRequest`` and can resolve it.

Only stdlib ``asyncio`` + ``json`` are used (via ``CodexRpcClient``); the
``codex_agent`` module imports no third-party dependency (Contract 9).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any

from coffer.application.chat.ports import ApprovalGate
from coffer.domain.chat.events import (
    AgentEvent,
    ApprovalRequest,
    TurnDone,
    TurnError,
    TurnStarted,
)
from coffer.domain.chat.message import Message
from coffer.infrastructure.chat.cli_agent import SessionSink, last_user_text
from coffer.infrastructure.chat.codex_app_server import (
    AppServerSessionFactory,
    CodexAppServerSession,
)
from coffer.infrastructure.chat.codex_jsonrpc import CodexRpcClient
from coffer.infrastructure.chat.codex_mapping import (
    CodexParseState,
    map_codex_notification,
)

_logger = logging.getLogger(__name__)

#: Sentinel pushed after the terminal event so ``_stream`` knows to stop.
_SENTINEL = object()

#: JSON-RPC client info Coffer announces in the ``initialize`` handshake.
_CLIENT_INFO = {"name": "coffer", "title": None, "version": "0"}

#: Scheduler turns a fileChange approval waits for its item's ``changes`` to
#: land via the pump before falling back to an empty-changes card.
_FILE_CHANGE_JOIN_TRIES = 8


class CodexAppServerAdapter:
    """One turn of an app-server-backed Codex agent, with per-tool approval relay.

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
        approvals: ApprovalGate,
    ) -> AsyncIterator[AgentEvent]:
        # Match the platform's ``async def -> AsyncIterator`` seam: delegate to
        # ``_stream`` so the coroutine machinery runs at yield points rather than
        # at the ``await run_turn(...)`` call site (the SDK adapter does the same).
        return self._stream(history, approvals)

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

    def _register_approval_handlers(
        self,
        rpc: CodexRpcClient,
        approvals: ApprovalGate,
        queue: asyncio.Queue[Any],
        file_changes: dict[str, Any],
    ) -> None:
        """Wire the server→client approval requests to the human approval gate.

        Each handler runs in ``CodexRpcClient``'s own task, so awaiting the human
        decision blocks only that task — the pump keeps draining and ``_stream``
        keeps yielding the ``ApprovalRequest``, so the orchestrator can resolve.
        """

        async def relay(
            request_id: str, tool_name: str, tool_input: dict[str, Any], *, allow: str, deny: str
        ) -> dict[str, Any]:
            await queue.put(
                ApprovalRequest(
                    request_id=request_id,
                    tool_use_id=request_id,
                    tool_name=tool_name,
                    tool_input=tool_input,
                )
            )
            decision = await approvals.wait(request_id)
            return {"decision": allow if decision.behavior == "allow" else deny}

        async def on_command(params: dict[str, Any]) -> dict[str, Any]:
            request_id = str(params.get("approvalId") or params.get("itemId") or "")
            return await relay(
                request_id,
                "shell",
                {"command": params.get("command"), "cwd": params.get("cwd")},
                allow="accept",
                deny="decline",
            )

        async def on_file_change(params: dict[str, Any]) -> dict[str, Any]:
            item_id = str(params.get("itemId") or "")
            request_id = str(params.get("approvalId") or item_id)
            # The approval params carry no contents — the ``changes`` come from
            # the matching ``fileChange`` item. That item's notification and this
            # handler are dispatched concurrently (handler in the RPC client's
            # task, item via the pump), so the join may not be populated yet;
            # yield to let the pump drain the preceding ``item/started`` (bounded
            # so a never-arriving item degrades to an empty-changes card, not a
            # hang).
            for _ in range(_FILE_CHANGE_JOIN_TRIES):
                if item_id in file_changes:
                    break
                await asyncio.sleep(0)
            changes = file_changes.get(item_id, [])
            return await relay(
                request_id,
                "file_change",
                {"changes": changes},
                allow="accept",
                deny="decline",
            )

        async def on_legacy_command(params: dict[str, Any]) -> dict[str, Any]:
            request_id = str(params.get("callId") or params.get("itemId") or "")
            command = params.get("command")
            return await relay(
                request_id,
                "shell",
                {"command": command, "cwd": params.get("cwd")},
                allow="approved",
                deny="denied",
            )

        async def on_legacy_patch(params: dict[str, Any]) -> dict[str, Any]:
            request_id = str(params.get("callId") or params.get("itemId") or "")
            return await relay(
                request_id,
                "file_change",
                {"changes": params.get("changes")},
                allow="approved",
                deny="denied",
            )

        # v2 (codex-cli 0.125.0) — the live surface.
        rpc.on_request("item/commandExecution/requestApproval", on_command)
        rpc.on_request("item/fileChange/requestApproval", on_file_change)
        # Legacy guard (T9) — cheap insurance for an older/future codex that
        # speaks the ``ReviewDecision`` (approved/denied) shape.
        rpc.on_request("execCommandApproval", on_legacy_command)
        rpc.on_request("applyPatchApproval", on_legacy_patch)

    async def _drive_handshake(self, rpc: CodexRpcClient, prompt: str) -> str:
        """Run initialize → initialized → thread/start|resume → turn/start.

        Returns the turn id (needed to interrupt). The thread id lands in the
        parse state via the ``thread/started`` notification the pump maps.
        """
        await rpc.request("initialize", {"clientInfo": _CLIENT_INFO, "capabilities": None})
        await rpc.notify("initialized")

        model = self._extra.get("model")
        if self._resume:
            thread_params: dict[str, Any] = {
                "threadId": self._resume,
                "cwd": self._cwd,
                "approvalPolicy": "on-request",
                "sandbox": "workspace-write",
            }
            if model:
                thread_params["model"] = model
            thread = await rpc.request("thread/resume", thread_params)
        else:
            thread_params = {
                "cwd": self._cwd,
                "approvalPolicy": "on-request",
                "sandbox": "workspace-write",
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
        self, history: Sequence[Message], approvals: ApprovalGate
    ) -> AsyncIterator[AgentEvent]:
        prompt = last_user_text(history)
        if not prompt:
            yield TurnError(code="empty_prompt", message="no user message to send")
            return

        state = CodexParseState(session_id=self._resume)
        queue: asyncio.Queue[Any] = asyncio.Queue()
        file_changes: dict[str, Any] = {}
        yield TurnStarted()

        session: CodexAppServerSession = self._session_factory(self._cwd, self._env)
        await session.start()
        rpc = session.rpc

        # Register approval handlers BEFORE starting the turn so an approval
        # request that arrives the instant the turn starts is never dropped.
        self._register_approval_handlers(rpc, approvals, queue, file_changes)

        async def pump() -> None:
            # Map streamed notifications onto the queue; the approval handlers
            # push ApprovalRequests onto the same queue so events interleave in
            # arrival order. A sentinel after the terminal event ends the drain.
            # The iterator ends when the RPC stream reaches EOF so a turn that
            # never sends ``turn/completed`` still terminates (the ``_stream``
            # tail then synthesizes a ``TurnDone``).
            try:
                async for method, params in _notifications_until_eof(rpc):
                    _track_file_change(method, params, file_changes)
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
    """Yield notifications, ending when the RPC read loop reaches EOF.

    ``CodexRpcClient.notifications()`` is an unbounded queue iterator that never
    stops on its own, so a turn whose peer closes the stream without a terminal
    notification would hang the pump. Race each fetch against the read task: when
    the read loop has finished AND no buffered notification remains, end cleanly
    so ``_stream`` can synthesize a terminal.
    """
    stream = rpc.notifications()
    read_task = rpc._read_task
    while True:
        nxt = asyncio.ensure_future(stream.__anext__())
        waiters: set[asyncio.Future[Any]] = {nxt}
        if read_task is not None:
            waiters.add(read_task)
        await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
        if nxt.done():
            yield nxt.result()
            continue
        # The read loop finished first. Give any notification produced in the
        # same tick a chance to land, then stop if none did.
        await asyncio.sleep(0)
        if nxt.done():
            yield nxt.result()
            continue
        nxt.cancel()
        with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration, Exception):
            await nxt
        return


def _track_file_change(method: str, params: dict[str, Any], file_changes: dict[str, Any]) -> None:
    """Record ``fileChange`` items by id so a later approval can join its changes.

    The ``item/fileChange/requestApproval`` params carry only the ``itemId`` —
    not the file contents — so the adapter keeps an ``itemId -> changes`` map
    populated from ``item/started`` / ``item/completed`` ``fileChange`` items.
    """
    if method not in ("item/started", "item/completed"):
        return
    item = params.get("item") or {}
    if item.get("type") != "fileChange":
        return
    item_id = item.get("id")
    if item_id is not None:
        file_changes[str(item_id)] = item.get("changes") or []


__all__ = ["CodexAppServerAdapter"]
