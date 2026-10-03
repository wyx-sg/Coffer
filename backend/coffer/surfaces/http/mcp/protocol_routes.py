"""/mcp — JSON-RPC over HTTP + SSE for downstream MCP clients."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from coffer.application.mcp.gateway import MCPGatewaySession
from coffer.application.runtime import correlation
from coffer.application.turn_ask import TURN_HEADER
from coffer.domain.errors import CofferError
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.mcp.dependencies import get_mcp_session_factory
from coffer.surfaces.http.mcp.session_registry import (
    _ACTIVE_SESSIONS as _ACTIVE_SESSIONS,
)
from coffer.surfaces.http.mcp.session_registry import (
    _DEFAULT_IDLE_TIMEOUT_S as _DEFAULT_IDLE_TIMEOUT_S,
)
from coffer.surfaces.http.mcp.session_registry import (
    _LAST_ACTIVITY as _LAST_ACTIVITY,
)
from coffer.surfaces.http.mcp.session_registry import (
    _NOTIFICATION_QUEUES as _NOTIFICATION_QUEUES,
)
from coffer.surfaces.http.mcp.session_registry import (
    _QUEUE_MAXSIZE as _QUEUE_MAXSIZE,
)
from coffer.surfaces.http.mcp.session_registry import (
    _REAPER_INTERVAL_S as _REAPER_INTERVAL_S,
)
from coffer.surfaces.http.mcp.session_registry import (
    _SESSION_DISPOSE_LOCKS as _SESSION_DISPOSE_LOCKS,
)
from coffer.surfaces.http.mcp.session_registry import (
    _SESSION_REFS as _SESSION_REFS,
)
from coffer.surfaces.http.mcp.session_registry import (
    _SESSION_STREAM_STOP as _SESSION_STREAM_STOP,
)
from coffer.surfaces.http.mcp.session_registry import (
    _STREAM_KEEPALIVE_S as _STREAM_KEEPALIVE_S,
)
from coffer.surfaces.http.mcp.session_registry import (
    _acquire_session_ref as _acquire_session_ref,
)
from coffer.surfaces.http.mcp.session_registry import (
    _drop_session as _drop_session,
)
from coffer.surfaces.http.mcp.session_registry import (
    _release_session_ref as _release_session_ref,
)
from coffer.surfaces.http.mcp.session_registry import (
    _release_stream as _release_stream,
)
from coffer.surfaces.http.mcp.session_registry import (
    _stream_stop_event as _stream_stop_event,
)
from coffer.surfaces.http.mcp.session_registry import (
    _touch as _touch,
)
from coffer.surfaces.http.mcp.session_registry import (
    reap_idle_sessions as reap_idle_sessions,
)
from coffer.surfaces.http.mcp.session_registry import (
    shutdown_all_sessions as shutdown_all_sessions,
)
from coffer.surfaces.http.mcp.session_registry import (
    start_session_reaper as start_session_reaper,
)

router = APIRouter(prefix="/mcp", tags=["mcp"], dependencies=[Depends(require_token)])
_logger = logging.getLogger(__name__)

#: Ids that start with this belong to the daemon's own supervisor registry
#: (``app_mcp_composition._PROCESS_SUPERVISOR_KEY``), not to a client's session.
RESERVED_SESSION_PREFIX = "__"

# JSON-RPC error codes
_JSON_RPC_INVALID_REQUEST = -32600
_JSON_RPC_INTERNAL_ERROR = -32603
_JSON_RPC_COFFER_TOOL_DISABLED = -32000


async def _get_or_create_session(
    session_id: str,
    factory: Callable[[str], MCPGatewaySession],
) -> MCPGatewaySession:
    _touch(session_id)
    if session_id in _ACTIVE_SESSIONS:
        return _ACTIVE_SESSIONS[session_id]
    session = factory(session_id)
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


def _session_not_found(req_id: Any) -> JSONResponse:
    """MCP streamable-http: an unknown session is 404, and the client must
    initialize a new one."""
    return JSONResponse(
        status_code=404,
        content=_error_response(req_id, _JSON_RPC_INVALID_REQUEST, "unknown session"),
    )


@router.post("", response_class=Response)
async def handle_post(
    request: Request,
    mcp_session_id: str | None = Header(default=None, alias="Mcp-Session-Id"),
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

    # Allocate a session id on the first request if the client sent none. A
    # session id this daemon does not know (the idle reaper dropped it, or the
    # daemon restarted) is answered 404 for anything but ``initialize``, so the
    # client handshakes again: rebuilding the session silently would lose the
    # agent identity and per-agent scope that ``initialize`` carried (spec
    # mcp-gateway "Take the agent identity from the handshake").
    if mcp_session_id is not None and mcp_session_id.startswith(RESERVED_SESSION_PREFIX):
        # A client names its own session id, so one that starts the way the
        # composition root's registry keys do (``__process__``) is never taken
        # as an id: it would replace that entry and blind the lifecycle hooks.
        mcp_session_id = None
    if (
        mcp_session_id is not None
        and mcp_session_id not in _ACTIVE_SESSIONS
        and (method != "initialize")
    ):
        return _session_not_found(req_id)
    session_id = mcp_session_id or str(uuid.uuid4())
    correlation.bind(session_id=session_id)
    session = await _get_or_create_session(session_id, factory)
    # The Coffer-run turn this agent process belongs to, when the shim reports one.
    session.turn_token = request.headers.get(TURN_HEADER) or None

    # Hold a refcount across the request so a concurrent SSE-close-triggered
    # _drop_session waits for us to finish before disposing the session.
    _acquire_session_ref(session_id)
    try:
        # Sampling and roots: if the envelope has no "method" but has an "id", it is a
        # JSON-RPC response to a server-initiated request that coffer sent downstream.
        # Route it to the session's pending-request registry and return 200 immediately.
        if method is None and req_id is not None:
            matched = session.handle_response_from_downstream(envelope)
            if matched:
                # Ack with a genuinely EMPTY body. JSONResponse("")
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
                if e.code == "TOOL_DISABLED"
                else _JSON_RPC_INTERNAL_ERROR
            )
            response: dict[str, Any] = _error_response(req_id, code, str(e))
        except Exception as e:
            # Never echo an arbitrary exception message onto the wire —
            # upstream/library errors can embed secrets (e.g. an auth
            # failure that reflects the API key). This branch only ever catches
            # non-CofferError exceptions (CofferError is handled above), so the
            # class name alone is the safe summary; the full detail is logged
            # server-side via ``_logger.exception``. Mirrors the invocation-log
            # rule in ``gateway_handlers._safe_error_summary`` (spec secret
            # "Hold plaintext only in memory at the moment of use").
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
    factory: Callable[[str], MCPGatewaySession] = Depends(get_mcp_session_factory),  # noqa: B008
) -> EventSourceResponse:
    """Open the SSE stream for downstream-bound server notifications."""
    if mcp_session_id is None:
        # MCP streamable-http clients always present a session id by GET time
        # (after the POST initialize). Reject anonymous GETs explicitly.
        raise HTTPException(status_code=400, detail="Mcp-Session-Id header required for GET /mcp")

    # A stream is opened only on a session ``initialize`` created; an unknown id
    # is 404 so the client handshakes again (see ``handle_post``).
    if mcp_session_id not in _ACTIVE_SESSIONS:
        raise HTTPException(status_code=404, detail="unknown session")
    _touch(mcp_session_id)
    queue = _NOTIFICATION_QUEUES.setdefault(mcp_session_id, asyncio.Queue(maxsize=_QUEUE_MAXSIZE))

    stop_event = _stream_stop_event(mcp_session_id)

    async def event_stream() -> AsyncIterator[dict[str, Any]]:
        # Emit an SSE comment immediately so the client sees the response
        # headers without waiting for the first real notification.
        yield {"comment": "connected"}
        try:
            while True:
                # Race the next notification against the session-stop
                # signal so a reaper-initiated drop wakes this parked generator
                # instead of leaving it blocked on a queue nobody will fill.
                getter = asyncio.ensure_future(queue.get())
                stopper = asyncio.ensure_future(stop_event.wait())
                try:
                    done, _ = await asyncio.wait(
                        {getter, stopper},
                        timeout=_STREAM_KEEPALIVE_S,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                finally:
                    # asyncio.wait never cancels what it waits on — not even
                    # when this generator is cancelled by a client disconnect.
                    # A leftover getter would stay parked on the session queue
                    # until the reaper drops it, then be garbage-collected as
                    # "Task was destroyed but it is pending!".
                    for task in (getter, stopper):
                        if not task.done():
                            task.cancel()
                if not done:
                    # Nothing arrived: an open stream is a live client, so it
                    # keeps the session out of the idle reaper's hands.
                    _touch(mcp_session_id)
                    continue
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
