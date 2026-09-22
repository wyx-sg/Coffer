"""Mark the daemon as wanted, once per request it actually serves.

The idle clock this feeds (:mod:`coffer.infrastructure.daemon.activity`) is
what lets a resident daemon stand down after a long enough silence, so what
counts as "wanted" is a real decision and it is made here: a request that got
past the host guard and reached the application. A DNS-rebinding attempt the
guard refuses is traffic, not use, and counting it would keep the daemon
resident on the strength of an attack.

A request counts for as long as it is *open*, not just at the instant it
arrives. ``/mcp`` is served over SSE and an agent's shim holds that stream for
the whole session, so an arrival-only clock would read a connected agent that
has not called a tool since last night as nobody at all.

Raw ASGI rather than ``BaseHTTPMiddleware``, for the reason
:mod:`coffer.surfaces.http.host_guard` gives: that base class buffers, which
breaks the long-lived SSE streams ``/mcp`` serves. Nothing here touches the
message stream anyway — it brackets the call and gets out of the way,
including when the application raises, since a request that failed still
wanted an answer from this daemon.
"""

from __future__ import annotations

from fastapi import FastAPI
from starlette.types import ASGIApp, Receive, Scope, Send

from coffer.infrastructure.daemon import activity


class ActivityMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        activity.request_started()
        try:
            await self.app(scope, receive, send)
        finally:
            activity.request_ended()


def install(app: FastAPI) -> None:
    app.add_middleware(ActivityMiddleware)
