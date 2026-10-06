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
from mcp import MCPError
from sse_starlette.sse import EventSourceResponse

from coffer.application.mcp.gateway import MCPGatewaySession
from coffer.application.mcp.gateway_inflight import RequestCancelled
from coffer.application.runtime import correlation
from coffer.application.turn_ask import TURN_HEADER
from coffer.domain.errors import CofferError
from coffer.domain.mcp.jsonrpc_errors import (
    INTERNAL_ERROR,
    INVALID_REQUEST,
    PARSE_ERROR,
    JsonRpcError,
)
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.mcp.dependencies import get_mcp_session_factory
from coffer.surfaces.http.mcp.jsonrpc import (
    METHOD_NOT_FOUND,
    REQUEST_METHODS,
    check_envelope,
    check_params,
    error_body,
    error_for,
)
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

_JSON_RPC_INVALID_REQUEST = INVALID_REQUEST
_JSON_RPC_INTERNAL_ERROR = INTERNAL_ERROR
#: The header naming the MCP version agreed at ``initialize``.
PROTOCOL_HEADER = "MCP-Protocol-Version"


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


def _session_not_found(req_id: Any) -> JSONResponse:
    """MCP streamable-http: an unknown session is 404, and the client must
    initialize a new one."""
    return JSONResponse(
        status_code=404,
        content=error_body(req_id, _JSON_RPC_INVALID_REQUEST, "unknown session"),
    )


def _protocol_header_refusal(request: Request, session: MCPGatewaySession) -> JSONResponse | None:
    """MCP Streamable HTTP: after ``initialize`` the client names the agreed
    version in ``MCP-Protocol-Version``; an unsupported or different one is 400.
    A request without the header is taken as the agreed version (the shim, and
    clients of the 2025-03-26 transport, send none)."""
    sent = request.headers.get(PROTOCOL_HEADER)
    if sent is None or sent == session.protocol_version:
        return None
    return JSONResponse(
        status_code=400,
        content=error_body(
            None, _JSON_RPC_INVALID_REQUEST, f"unsupported {PROTOCOL_HEADER}: {sent!r}"
        ),
    )


@router.post("", response_class=Response)
async def handle_post(
    request: Request,
    mcp_session_id: str | None = Header(default=None, alias="Mcp-Session-Id"),
    factory: Callable[[str], MCPGatewaySession] = Depends(get_mcp_session_factory),  # noqa: B008
) -> Any:
    """Process one JSON-RPC message from a downstream MCP client (spec
    mcp-gateway "Answer every MCP message by the JSON-RPC rules")."""
    try:
        envelope = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content=error_body(None, PARSE_ERROR, "invalid JSON"))
    req_id, malformed = check_envelope(envelope)
    if malformed is not None:
        return JSONResponse(content=error_body(req_id, malformed.code, malformed.message))
    method = envelope.get("method")
    params = envelope.get("params", {})
    is_request = "id" in envelope

    if mcp_session_id is not None and mcp_session_id.startswith(RESERVED_SESSION_PREFIX):
        # A client names its own session id, so one that starts the way the
        # composition root's registry keys do (``__process__``) is never taken
        # as an id: it would replace that entry and blind the lifecycle hooks.
        mcp_session_id = None
    if method == "initialize":
        try:
            check_params(method, params)
        except JsonRpcError as e:
            return JSONResponse(content=error_body(req_id, e.code, e.message))
    elif mcp_session_id is None:
        # Only ``initialize`` opens a session; anything else without one is 400.
        return JSONResponse(
            status_code=400,
            content=error_body(req_id, _JSON_RPC_INVALID_REQUEST, "Mcp-Session-Id header required"),
        )
    elif mcp_session_id not in _ACTIVE_SESSIONS:
        # A session id this daemon does not know (the idle reaper dropped it,
        # or the daemon restarted) is 404, so the client handshakes again:
        # rebuilding it silently would lose the agent identity and scope that
        # ``initialize`` carried (spec mcp-gateway "Take the agent identity from
        # the handshake").
        return _session_not_found(req_id)
    session_id = mcp_session_id or str(uuid.uuid4())
    correlation.bind(session_id=session_id)
    session = await _get_or_create_session(session_id, factory)
    # The Coffer-run turn this agent process belongs to, when the shim reports one.
    session.turn_token = request.headers.get(TURN_HEADER) or None
    headers = {"Mcp-Session-Id": session_id}
    if method != "initialize" and session.protocol_version is not None:
        refusal = _protocol_header_refusal(request, session)
        if refusal is not None:
            return refusal

    # Hold a refcount across the request so a concurrent SSE-close-triggered
    # _drop_session waits for us to finish before disposing the session.
    _acquire_session_ref(session_id)
    try:
        if method is None:
            # A response to a request Coffer sent downstream (sampling, roots).
            # Matched or not, a response gets no response: an empty 202 (a body
            # of ``""`` would reach the shim's MCP wire as a stray line).
            if not session.handle_response_from_downstream(envelope):
                _logger.info("mcp.post.unmatched_response", extra={"id": req_id})
            return Response(status_code=202, headers=headers)
        if not is_request:
            # A notification never gets a response body.
            _on_notification(session, method, params)
            return Response(status_code=202, headers=headers)
        try:
            if method != "initialize" and session.protocol_version is None:
                raise JsonRpcError(_JSON_RPC_INVALID_REQUEST, "the session is not initialized")
            if method not in REQUEST_METHODS:
                raise JsonRpcError(METHOD_NOT_FOUND, f"method not found: {method!r}")
            check_params(method, params)
            if method == "initialize":
                result = await session.handle_initialize(params)
            elif method == "ping":
                result = {}
            else:
                result = await session.inflight.run(req_id, session.handle_request(method, params))
        except RequestCancelled:
            # The client cancelled it: MCP sends no response for that request.
            return Response(status_code=202, headers=headers)
        except Exception as e:
            if not isinstance(e, (CofferError, JsonRpcError, MCPError)):
                # Never echo an arbitrary exception message onto the wire —
                # upstream/library errors can embed secrets; the class name is
                # the safe summary and the detail goes to the daemon log.
                _logger.exception("mcp.post.unexpected", extra={"method": method})
            code, message = error_for(e)
            response: dict[str, Any] = error_body(req_id, code, message)
        else:
            response = {"jsonrpc": "2.0", "id": req_id, "result": result}
        return JSONResponse(content=response, headers=headers)
    finally:
        _release_session_ref(session_id)


def _on_notification(session: MCPGatewaySession, method: str, params: dict[str, Any]) -> None:
    """``notifications/cancelled`` cancels that request of THIS session; every
    other notification needs nothing from the gateway."""
    if method == "notifications/cancelled":
        request_id = params.get("requestId")
        if isinstance(request_id, (str, int)) and not isinstance(request_id, bool):
            session.inflight.cancel(request_id)


@router.get("", response_class=Response)
async def handle_get(
    mcp_session_id: str | None = Header(default=None, alias="Mcp-Session-Id"),
    factory: Callable[[str], MCPGatewaySession] = Depends(get_mcp_session_factory),  # noqa: B008
    sent: str | None = Header(default=None, alias=PROTOCOL_HEADER),
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
    # ``isinstance``: a direct call (tests) leaves the parameter at its Header default.
    if isinstance(sent, str) and sent != _ACTIVE_SESSIONS[mcp_session_id].protocol_version:
        raise HTTPException(status_code=400, detail=f"unsupported {PROTOCOL_HEADER}: {sent!r}")
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
