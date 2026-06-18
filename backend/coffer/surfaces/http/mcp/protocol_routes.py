"""/mcp — JSON-RPC over HTTP + SSE for downstream MCP clients."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from coffer.application.mcp.gateway import MCPGatewaySession
from coffer.domain.errors import CofferError
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_mcp_session_factory

router = APIRouter(prefix="/mcp", tags=["mcp"], dependencies=[Depends(require_token)])
_logger = logging.getLogger(__name__)

# JSON-RPC error codes
_JSON_RPC_INVALID_REQUEST = -32600
_JSON_RPC_METHOD_NOT_FOUND = -32601
_JSON_RPC_INVALID_PARAMS = -32602
_JSON_RPC_INTERNAL_ERROR = -32603
_JSON_RPC_COFFER_TOOL_DISABLED = -32000

# A notification-queue caps the worst-case memory a misbehaving upstream can
# consume while no downstream client is draining the SSE stream. When the
# queue is full we drop the oldest message — keeping the latest event is
# more useful than blocking the upstream.
_QUEUE_MAXSIZE = 1000

# Default idle timeout for the session reaper. A session is considered idle
# when neither a POST nor an upstream notification has touched it for this
# many seconds. Conservative default lets long-lived clients stay connected
# while still bounding leaked-session memory. The ``start_session_reaper``
# constructor knobs override these (CODE-022); env wiring is
# ``COFFER_MCP_SESSION_IDLE_S`` / ``COFFER_MCP_SESSION_REAPER_INTERVAL_S``.
_DEFAULT_IDLE_TIMEOUT_S = 30 * 60

# How often the session reaper wakes up.
_REAPER_INTERVAL_S = 60

# Per-session notification queues (process-local).
# Key: session_id; Value: bounded asyncio.Queue[str] of pre-serialised JSON payloads.
_NOTIFICATION_QUEUES: dict[str, asyncio.Queue[str]] = {}

# Per-session MCPGatewaySession instances.
_ACTIVE_SESSIONS: dict[str, MCPGatewaySession] = {}

# Per-session last-activity timestamp (time.monotonic()). Updated on every
# downstream POST and every upstream-originated sink push. Used by the
# session reaper to evict idle sessions.
_LAST_ACTIVITY: dict[str, float] = {}

# Per-session in-flight POST refcount. _drop_session() waits for this to
# reach zero before disposing the gateway session so a concurrent POST
# handler that is mid-request never sees a half-disposed session
# (CODE-017). Keyed by session_id; absent entries imply 0 refs.
_SESSION_REFS: dict[str, int] = {}
# Per-session lock guarding the dispose path so only one _drop_session
# runs at a time per session. asyncio.Lock is cheap and lives for the
# session's lifetime.
_SESSION_DISPOSE_LOCKS: dict[str, asyncio.Lock] = {}

# CODE-040: per-session "stream should stop" signal. An idle GET /mcp SSE
# generator parks on ``queue.get()``; when the reaper drops the session it
# pops the queue but the generator keeps its own reference and would block
# forever, leaking the HTTP connection + task. _drop_session sets this event
# so the parked generator wakes and terminates cleanly.
_SESSION_STREAM_STOP: dict[str, asyncio.Event] = {}


def _stream_stop_event(session_id: str) -> asyncio.Event:
    return _SESSION_STREAM_STOP.setdefault(session_id, asyncio.Event())


def _touch(session_id: str) -> None:
    _LAST_ACTIVITY[session_id] = time.monotonic()


def _acquire_session_ref(session_id: str) -> None:
    _SESSION_REFS[session_id] = _SESSION_REFS.get(session_id, 0) + 1


def _release_session_ref(session_id: str) -> None:
    current = _SESSION_REFS.get(session_id, 0)
    if current <= 1:
        _SESSION_REFS.pop(session_id, None)
    else:
        _SESSION_REFS[session_id] = current - 1


async def _get_or_create_session(
    session_id: str,
    factory: Callable[[str], MCPGatewaySession],
    agent_name: str | None = None,
) -> MCPGatewaySession:
    _touch(session_id)
    if session_id in _ACTIVE_SESSIONS:
        session = _ACTIVE_SESSIONS[session_id]
        session.bind_agent(agent_name)
        return session
    session = factory(session_id)
    session.bind_agent(agent_name)
    queue = _NOTIFICATION_QUEUES.setdefault(session_id, asyncio.Queue(maxsize=_QUEUE_MAXSIZE))

    async def _sink(payload: dict[str, Any]) -> None:
        message = json.dumps({"jsonrpc": "2.0", **payload}, default=str)
        # Drop-oldest on full: prevents a noisy upstream from filling memory
        # while the downstream client is slow/absent. The latest notification
        # wins because clients typically rebuild state on reconnect from
        # the most recent server view.
        while True:
            try:
                queue.put_nowait(message)
                break
            except asyncio.QueueFull:
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                _logger.warning(
                    "mcp.sse.queue.dropped_oldest",
                    extra={"session": session_id, "maxsize": _QUEUE_MAXSIZE},
                )
        _touch(session_id)

    session.set_downstream_sink(_sink)
    _ACTIVE_SESSIONS[session_id] = session
    return session


def _error_response(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": code, "message": message},
    }


@router.post("", response_class=Response)
async def handle_post(
    request: Request,
    mcp_session_id: str | None = Header(default=None, alias="Mcp-Session-Id"),
    x_coffer_agent: str | None = Header(default=None, alias="X-Coffer-Agent"),
    factory: Callable[[str], MCPGatewaySession] = Depends(get_mcp_session_factory),  # noqa: B008
) -> Any:
    """Process one JSON-RPC request from a downstream MCP client."""
    try:
        envelope = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON") from None

    # The body parsed as valid JSON but must be a JSON-RPC request object. A
    # top-level array (batch) or scalar has no "id"/"method" to read — reject
    # it as an invalid request rather than crashing on ``.get`` (→ opaque 500).
    if not isinstance(envelope, dict):
        return JSONResponse(
            content=_error_response(None, _JSON_RPC_INVALID_REQUEST, "invalid request"),
        )

    req_id = envelope.get("id")
    method = envelope.get("method")
    params = envelope.get("params") or {}

    # Allocate a session id on the very first request if the client didn't send one.
    session_id = mcp_session_id or str(uuid.uuid4())
    session = await _get_or_create_session(session_id, factory, x_coffer_agent)

    # Hold a refcount across the request so a concurrent SSE-close-triggered
    # _drop_session waits for us to finish before disposing the session
    # (CODE-017).
    _acquire_session_ref(session_id)
    try:
        # T-061/T-062: if the envelope has no "method" but has an "id", it is a
        # JSON-RPC response to a server-initiated request that coffer sent downstream.
        # Route it to the session's pending-request registry and return 200 immediately.
        if method is None and req_id is not None:
            matched = session.handle_response_from_downstream(envelope)
            if matched:
                # CODE-029: ack with a genuinely EMPTY body. JSONResponse("")
                # serialises to the 2-byte body `""` (a JSON empty-string),
                # which the shim parses as valid JSON and forwards as a stray
                # line on the MCP wire, corrupting the downstream client. A
                # bare 202 with no body is the contract the shim expects for a
                # matched-response ack.
                return Response(status_code=202, headers={"Mcp-Session-Id": session_id})
            # Non-matching id with no method — fall through to the "missing method" error.

        if not isinstance(method, str):
            return _error_response(req_id, _JSON_RPC_INVALID_REQUEST, "missing method")

        # Notifications are one-way messages: they have no "id" and must never
        # receive a JSON-RPC response body.  Return 202 Accepted immediately for
        # any no-id message — whether it starts with "notifications/" or not
        # (e.g. a bare "ping" sent as a notification).
        if req_id is None:
            return Response(status_code=202, headers={"Mcp-Session-Id": session_id})

        try:
            if method == "initialize":
                result = await session.handle_initialize(params)
            elif method == "ping":
                result = {}
            else:
                result = await session.handle_request(method, params)
        except CofferError as e:
            code = (
                _JSON_RPC_COFFER_TOOL_DISABLED
                if e.code in ("TOOL_DISABLED", "MCP_SERVER_OUT_OF_SCOPE")
                else _JSON_RPC_INTERNAL_ERROR
            )
            response: dict[str, Any] = _error_response(req_id, code, str(e))
        except Exception as e:
            # CODE-M1: never echo an arbitrary exception message onto the wire —
            # upstream/library errors can embed credentials (e.g. an auth
            # failure that reflects the API key). This branch only ever catches
            # non-CofferError exceptions (CofferError is handled above), so the
            # class name alone is the safe summary; the full detail is logged
            # server-side via ``_logger.exception``. Mirrors the invocation-log
            # rule in ``gateway_handlers._safe_error_summary`` (SC-010).
            _logger.exception("mcp.post.unexpected", extra={"method": method})
            response = _error_response(
                req_id, _JSON_RPC_INTERNAL_ERROR, f"internal error: {type(e).__name__}"
            )
        else:
            response = {"jsonrpc": "2.0", "id": req_id, "result": result}

        # Per the MCP streamable-http spec, return the session id so the client
        # uses it on subsequent calls.
        return JSONResponse(
            content=response,
            headers={"Mcp-Session-Id": session_id},
        )
    finally:
        _release_session_ref(session_id)


@router.get("", response_class=Response)
async def handle_get(
    mcp_session_id: str | None = Header(default=None, alias="Mcp-Session-Id"),
    x_coffer_agent: str | None = Header(default=None, alias="X-Coffer-Agent"),
    factory: Callable[[str], MCPGatewaySession] = Depends(get_mcp_session_factory),  # noqa: B008
) -> EventSourceResponse:
    """Open the SSE stream for downstream-bound server notifications."""
    if mcp_session_id is None:
        # MCP streamable-http clients always present a session id by GET time
        # (after the POST initialize). Reject anonymous GETs explicitly.
        raise HTTPException(status_code=400, detail="Mcp-Session-Id header required for GET /mcp")

    # Ensure the session exists (might not yet have received its first POST)
    await _get_or_create_session(mcp_session_id, factory, x_coffer_agent)
    queue = _NOTIFICATION_QUEUES.setdefault(mcp_session_id, asyncio.Queue(maxsize=_QUEUE_MAXSIZE))

    stop_event = _stream_stop_event(mcp_session_id)

    async def event_stream() -> AsyncIterator[dict[str, Any]]:
        # Emit an SSE comment immediately so the client sees the response
        # headers without waiting for the first real notification.
        yield {"comment": "connected"}
        try:
            while True:
                # CODE-040: race the next notification against the session-stop
                # signal so a reaper-initiated drop wakes this parked generator
                # instead of leaving it blocked on a queue nobody will fill.
                getter = asyncio.ensure_future(queue.get())
                stopper = asyncio.ensure_future(stop_event.wait())
                done, pending = await asyncio.wait(
                    {getter, stopper}, return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                if getter in done:
                    payload = getter.result()
                    _touch(mcp_session_id)
                    yield {"event": "message", "data": payload}
                else:
                    # Session is being disposed — end the stream cleanly.
                    return
        except asyncio.CancelledError:
            # Client closed the SSE stream. Release ONLY the stream, never the
            # session: the shim reconnects its GET stream routinely (proxy
            # timeouts, network blips) and immediately re-opens it on the same
            # Mcp-Session-Id. Disposing the session here would tear down the
            # upstream subprocess connections within seconds and defeat that
            # reconnect design — a reconnecting client would find its upstreams
            # gone. Session disposal is owned solely by the idle reaper, which
            # only drops a session after it has been untouched past the idle
            # window. The shared stream-stop event is reset so the next GET on
            # the same session parks cleanly instead of returning immediately.
            _release_stream(mcp_session_id)
            raise

    return EventSourceResponse(event_stream())


def _release_stream(session_id: str) -> None:
    """Tear down per-stream state for a closed SSE connection, leaving the
    session itself intact for reuse / the idle reaper.

    A single stream-stop event is shared per session id; clearing it (rather
    than popping it) keeps the same object the next GET looks up via
    ``_stream_stop_event`` while ensuring that next stream starts un-signalled.
    """
    if (ev := _SESSION_STREAM_STOP.get(session_id)) is not None:
        ev.clear()


# Maximum number of 100ms polls _drop_session will perform waiting for an
# in-flight POST to release its refcount before forcibly disposing.
_DROP_WAIT_MAX_POLLS = 50


async def _drop_session(session_id: str) -> None:
    """Dispose a session, waiting for any in-flight POST to drain first.

    Concurrent POST handlers acquire a refcount via ``_acquire_session_ref``;
    this function spins (up to ~5 s) until that count is zero and then
    swaps the session out atomically inside a per-session lock so two
    concurrent _drop_session calls cannot double-dispose (CODE-017).
    """
    lock = _SESSION_DISPOSE_LOCKS.setdefault(session_id, asyncio.Lock())
    async with lock:
        # CODE-040: wake any parked SSE generator for this session so it
        # terminates instead of blocking forever on the about-to-be-dropped
        # queue. Set before the refcount wait so the stream unwinds promptly.
        if (ev := _SESSION_STREAM_STOP.get(session_id)) is not None:
            ev.set()

        # Wait briefly for in-flight POSTs to release their refcount. We
        # bound the wait so a stuck handler can't keep memory pinned forever.
        for _ in range(_DROP_WAIT_MAX_POLLS):
            if _SESSION_REFS.get(session_id, 0) == 0:
                break
            await asyncio.sleep(0.1)

        session = _ACTIVE_SESSIONS.pop(session_id, None)
        _NOTIFICATION_QUEUES.pop(session_id, None)
        _LAST_ACTIVITY.pop(session_id, None)
        _SESSION_REFS.pop(session_id, None)
        _SESSION_STREAM_STOP.pop(session_id, None)
        if session is not None:
            with contextlib.suppress(Exception):
                await session.dispose()
    # Drop the lock entry only after release so future _drop_session calls
    # for the same id (rare; usually a no-op anyway) get a fresh lock.
    _SESSION_DISPOSE_LOCKS.pop(session_id, None)


async def shutdown_all_sessions() -> None:
    """Called by app lifespan on shutdown."""
    for sid in list(_ACTIVE_SESSIONS.keys()):
        await _drop_session(sid)


async def reap_idle_sessions(max_idle_seconds: float = _DEFAULT_IDLE_TIMEOUT_S) -> list[str]:
    """Drop sessions whose last activity is older than ``max_idle_seconds``.

    Returns the list of dropped session ids (useful for logging/testing).
    """
    now = time.monotonic()
    stale = [sid for sid, last in list(_LAST_ACTIVITY.items()) if now - last > max_idle_seconds]
    for sid in stale:
        await _drop_session(sid)
    return stale


async def _session_reaper_loop(interval_seconds: float, max_idle_seconds: float) -> None:
    """Periodically reap idle sessions until cancelled."""
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            stale = await reap_idle_sessions(max_idle_seconds)
            if stale:
                _logger.info(
                    "mcp.session.reaped",
                    extra={"count": len(stale), "session_ids": stale},
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            _logger.exception("mcp.session.reaper_failed")


def start_session_reaper(
    *,
    interval_seconds: float = _REAPER_INTERVAL_S,
    max_idle_seconds: float = _DEFAULT_IDLE_TIMEOUT_S,
) -> asyncio.Task[None]:
    """Spawn the background session reaper task. Caller must cancel on shutdown."""
    return asyncio.create_task(
        _session_reaper_loop(interval_seconds, max_idle_seconds),
        name="mcp-session-reaper",
    )
