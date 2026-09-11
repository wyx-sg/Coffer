"""Reject any request not addressed to a loopback authority (DNS rebinding).

The daemon binds loopback only, which stops a *remote* host from reaching it.
It does not stop a **browser** from reaching it: a page on ``evil.com`` whose
hostname the attacker re-resolves to ``127.0.0.1`` is, as far as the browser is
concerned, still same-origin with ``evil.com`` — so every same-origin
protection (CORS, the empty allowlist in :mod:`coffer.surfaces.http.cors`)
lets the page read the response body.

That used to be survivable because the daemon's responses held nothing a
rebound page could use without the token. It stopped being survivable the
moment the served ``index.html`` began carrying the live API token
(:mod:`coffer.surfaces.http.webui`): one ``fetch("/")`` would hand the whole
vault over.

The defence is the ``Host`` header, and it works precisely because rebinding
does *not* change it — the browser sends the hostname from the URL it fetched,
so a rebound request still says ``Host: evil.com``. A request that genuinely
reached the daemon over loopback says ``127.0.0.1``, ``localhost`` or ``::1``.
Comparing the two is the whole check.

``COFFER_ALLOWED_HOSTS`` (comma-separated, or ``*``) adds authorities beyond
the loopback set. The backend test suite sets ``*`` because it drives the ASGI
app in-process, where there is no network and therefore no rebinding to defend
against; the guard's own tests clear it. Nothing in a real deployment should
need it.
"""

from __future__ import annotations

import ipaddress
import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

#: Hostnames that are loopback but are not IP literals.
_LOOPBACK_NAMES: frozenset[str] = frozenset({"localhost"})

#: 421 Misdirected Request: the request reached a server that is not willing to
#: answer for the authority it names. That is exactly this situation, and it is
#: distinguishable from the 401 a wrong token produces.
_STATUS_MISDIRECTED = 421

_ERROR_CODE = "HOST_NOT_LOOPBACK"


def _allowed_extra() -> tuple[str, ...]:
    raw = os.environ.get("COFFER_ALLOWED_HOSTS", "")
    return tuple(part.strip().lower() for part in raw.split(",") if part.strip())


def _hostname_of(authority: str) -> str | None:
    """The host part of a ``Host`` header, port stripped. None when unparseable.

    Three shapes have to survive: ``127.0.0.1:8000``, ``[::1]:8000`` and a bare
    ``::1`` (no brackets, no port — some clients send it that way).
    """
    value = authority.strip()
    if not value:
        return None
    if value.startswith("["):
        close = value.find("]")
        if close < 0:
            return None
        rest = value[close + 1 :]
        if rest and not rest.startswith(":"):
            return None
        return value[1:close]
    if value.count(":") > 1:
        # Bare IPv6 literal — every colon belongs to the address, none to a port.
        return value
    head, _, tail = value.rpartition(":")
    return head if head and tail.isdigit() else value


def is_loopback_authority(authority: str | None) -> bool:
    """Whether ``authority`` names this machine's loopback interface.

    A missing ``Host`` is not loopback. No browser omits it, so rejecting the
    empty case costs nothing and keeps the rule a single sentence.
    """
    if authority is None:
        return False
    extra = _allowed_extra()
    if "*" in extra:
        return True
    hostname = _hostname_of(authority)
    if hostname is None:
        return False
    lowered = hostname.lower()
    if lowered in _LOOPBACK_NAMES or lowered in extra:
        return True
    try:
        return ipaddress.ip_address(lowered).is_loopback
    except ValueError:
        return False


class LoopbackHostMiddleware:
    """Raw ASGI middleware — deliberately not ``BaseHTTPMiddleware``.

    ``BaseHTTPMiddleware`` buffers through an anyio stream, which interferes
    with the long-lived SSE streams ``/mcp`` serves. This one only inspects a
    header before delegating, so it stays out of the body's way entirely.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        host = Headers(scope=scope).get("host")
        if is_loopback_authority(host):
            await self.app(scope, receive, send)
            return
        response = JSONResponse(
            status_code=_STATUS_MISDIRECTED,
            content={
                "error": {
                    "code": _ERROR_CODE,
                    "message": (
                        "Coffer only answers requests addressed to its loopback "
                        f"address; this one named {host or '(no Host header)'}."
                    ),
                    "details": None,
                }
            },
        )
        await response(scope, receive, send)


def install(app: FastAPI) -> None:
    """Wrap ``app`` so the check runs before anything else it hosts."""
    app.add_middleware(LoopbackHostMiddleware)
