"""Refuse a request not addressed to this daemon, or sent from a foreign page.

Spec daemon "Refuse a request whose Host or Origin is not the daemon's own".

The daemon binds loopback only, which stops a *remote* host from reaching it.
It does not stop a **browser**: any page the user has open can send requests
to ``127.0.0.1``. Two checks close that, and they run on every request the
daemon's one listener answers — the REST API, ``/mcp``, the SSE event stream,
any websocket and the served web UI alike, because they are all this one ASGI
app.

**Host (DNS rebinding).** A page on ``evil.com`` whose hostname the attacker
re-resolves to ``127.0.0.1`` is, to the browser, still same-origin with
``evil.com`` — so CORS never applies and the page can read the response body,
including the live API token the served ``index.html`` carries
(:mod:`coffer.surfaces.http.webui`). Rebinding does not change the ``Host``
header: the browser still sends the hostname from the URL it fetched. So the
``Host`` must name a loopback address (``127.0.0.1``, ``localhost``, ``[::1]``)
*and* the port the request actually arrived on. A request with no ``Host`` is
refused too; no browser omits it.

**Origin (cross-site requests).** A page on any other origin can still *send*
a request to the right ``Host`` — a form POST, an ``EventSource``, a
``fetch`` with ``mode: "no-cors"`` — even though it cannot read the answer.
The token makes such a request harmless today; this check makes it harmless
without leaning on that. A request that carries an ``Origin`` is refused
unless the origin is Coffer's own: the daemon's web origin on the port the
request arrived on (the browser tab it serves), or one of the cross-origin
hosts :func:`coffer.surfaces.http.cors.cross_origin_allowlist` names — the
desktop shell's origins always, the Vite dev origins only behind
``COFFER_DEV_CORS=1``, or exactly what ``COFFER_CORS_ORIGINS`` lists. A
request with **no** ``Origin`` — the CLI, the shim, an agent's MCP client,
``curl`` — is let through to the ordinary token check: only a browser sends
``Origin``, and a non-browser client could put any value it likes there anyway.

Both refusals are ``403`` with the error envelope, and each distinct refused
value is logged once (bounded), so a page retrying in a loop cannot flood the
daemon log.

``COFFER_ALLOWED_HOSTS`` (comma-separated, or ``*``) adds hostnames the Host
check accepts. The backend test suite sets ``*`` because it drives the ASGI
app in-process, where transports send made-up authorities like
``testserver``; the guard's own tests clear it. It never relaxes the Origin
check. Nothing in a real deployment should need it.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from coffer.infrastructure.net import loopback_authority
from coffer.surfaces.http import cors, daemon_routes

_logger = logging.getLogger(__name__)

#: The web-origin spellings of this daemon's own loopback address, before the
#: port is appended.
_OWN_ORIGIN_HOSTS: tuple[str, ...] = ("127.0.0.1", "localhost", "[::1]")

HOST_CODE = "HOST_NOT_ALLOWED"
ORIGIN_CODE = "ORIGIN_NOT_ALLOWED"

#: A websocket handshake closed before ``accept`` is answered with HTTP 403 by
#: the server; 1008 is "policy violation".
_WS_POLICY_VIOLATION = 1008

#: How many distinct refused values are remembered for log-once. Past this the
#: set stops growing and further new values are not logged — a hostile page
#: minting a fresh hostname per request cannot grow memory or the log.
_LOG_ONCE_CAP = 256
_logged: set[tuple[str, str]] = set()


def _allowed_extra() -> tuple[str, ...]:
    raw = os.environ.get("COFFER_ALLOWED_HOSTS", "")
    return tuple(part.strip().lower() for part in raw.split(",") if part.strip())


def is_allowed_host(authority: str | None, port: int) -> bool:
    """Whether ``authority`` names this machine's loopback address on ``port``.

    The predicate itself is shared with the model proxy
    (:func:`coffer.infrastructure.net.loopback_authority.is_allowed_host`);
    what is the daemon's own is the ``COFFER_ALLOWED_HOSTS`` escape hatch, which
    adds hostnames (``*`` accepts anything).
    """
    return loopback_authority.is_allowed_host(authority, port, _allowed_extra())


def own_origins(port: int) -> list[str]:
    """The daemon's own web origins on ``port`` — where the UI it serves runs."""
    return [f"http://{host}:{port}" for host in _OWN_ORIGIN_HOSTS]


def allowed_origins(port: int) -> list[str]:
    """Every origin a request may carry: the daemon's own plus the allowlist."""
    return own_origins(port) + cors.cross_origin_allowlist()


def is_allowed_origin(origin: str | None, port: int) -> bool:
    """Whether a request carrying ``origin`` may proceed. No Origin: yes."""
    if origin is None:
        return True
    wanted = origin.strip().lower().rstrip("/")
    return wanted in {o.lower().rstrip("/") for o in allowed_origins(port)}


def _listener_port(scope: Scope) -> int:
    """The port this request actually arrived on.

    Read off the connection rather than configuration, so every socket the
    server answers on checks against itself. The configured daemon port is the
    fallback for a transport that reports no server address.
    """
    server = scope.get("server")
    if server and len(server) >= 2 and isinstance(server[1], int):
        return server[1]
    return daemon_routes.get_port()


def _log_once(reason: str, value: str, path: str) -> None:
    key = (reason, value)
    if key in _logged or len(_logged) >= _LOG_ONCE_CAP:
        return
    _logged.add(key)
    _logger.warning(
        "http.request_refused",
        extra={"reason": reason, "value": value, "path": path},
    )


class LoopbackHostMiddleware:
    """Raw ASGI middleware — deliberately not ``BaseHTTPMiddleware``.

    ``BaseHTTPMiddleware`` buffers through an anyio stream, which interferes
    with the long-lived SSE streams ``/mcp`` and ``/api/v1/events`` serve. This
    one only inspects headers before delegating, so it stays out of the body's
    way entirely.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        port = _listener_port(scope)
        host = headers.get("host")
        origin = headers.get("origin")
        path = scope.get("path", "")
        if not is_allowed_host(host, port):
            shown = host or "(no Host header)"
            _log_once("host", shown, path)
            message = (
                f"Coffer only answers requests addressed to 127.0.0.1:{port} or "
                f"localhost:{port}; this one named {shown}."
            )
            await _refuse(scope, receive, send, HOST_CODE, message)
            return
        if not is_allowed_origin(origin, port):
            _log_once("origin", origin or "", path)
            message = f"Coffer does not accept requests from pages on {origin}."
            await _refuse(scope, receive, send, ORIGIN_CODE, message)
            return
        await self.app(scope, receive, send)


async def _refuse(scope: Scope, receive: Receive, send: Send, code: str, message: str) -> None:
    if scope["type"] == "websocket":
        await send({"type": "websocket.close", "code": _WS_POLICY_VIOLATION})
        return
    response = JSONResponse(
        status_code=403,
        content={"error": {"code": code, "message": message, "details": None}},
    )
    await response(scope, receive, send)


def install(app: FastAPI) -> None:
    """Wrap ``app`` so the check runs before anything else it hosts."""
    app.add_middleware(LoopbackHostMiddleware)
