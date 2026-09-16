"""Give every HTTP request a trace id, so a log line and a response can be tied
together.

``infrastructure.logging.setup`` has carried the machinery for this all along: a
``coffer_trace_id`` contextvar, a structlog processor that stamps ``trace_id``
on every record, and an ``X-Coffer-Trace`` header on every error envelope
(:mod:`coffer.surfaces.http.errors`). What it did not have was anything that
ever *set* the contextvar — so the log field and the header both read the
``"-"`` sentinel, on every request, forever. The facility existed and answered
nothing.

This middleware is the missing writer. It is the seam that makes
``coffer__diagnose`` work as intended: an agent handed a failed request's
``X-Coffer-Trace`` value can grep the daemon log for that id and find the
records the request produced, instead of guessing from timestamps.

A client may supply its own ``X-Coffer-Trace`` request header — the CLI and the
MCP shim both make several calls on one user action, and a shared id makes them
one story in the log. Anything a client sends is untrusted, so it is length-capped
and reduced to the characters an id may hold before it reaches a log line or a
response header; a value that survives none of that is replaced by a fresh one.

Raw ASGI, deliberately not ``BaseHTTPMiddleware``, for the reason
:mod:`coffer.surfaces.http.host_guard` gives: the buffering that base class does
interferes with the long-lived SSE streams ``/mcp`` serves. It also keeps the
contextvar set in the *same* task the route runs in, which is the only way the
route's own log records inherit it.
"""

from __future__ import annotations

import re
import uuid

from fastapi import FastAPI
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from coffer.infrastructure.logging.setup import bind_trace_id

#: The request header a client may use to supply its own id, and the response
#: header the daemon always answers with. One name, both directions.
TRACE_HEADER = "x-coffer-trace"

#: An id is an opaque correlation handle, so the accepted alphabet is only what
#: is safe to put in a header and read back out of a log file.
_ALLOWED = re.compile(r"[^A-Za-z0-9._:-]")

#: Long enough for a UUID hex or an upstream request id; short enough that a
#: hostile client cannot pad the log with one header.
_MAX_LEN = 64


def new_trace_id() -> str:
    """A fresh id. Half a UUID is plenty to separate concurrent requests."""
    return uuid.uuid4().hex[:16]


def sanitize_trace_id(raw: str | None) -> str:
    """The id to use for this request: the client's, cleaned, or a new one.

    Cleaning is lossy on purpose. The id is never parsed, only matched, so a
    value that loses characters still correlates with itself — while a value
    carrying a newline would forge a log record, and one carrying a control
    character would corrupt the response header.
    """
    if not raw:
        return new_trace_id()
    cleaned = _ALLOWED.sub("", raw.strip())[:_MAX_LEN]
    return cleaned or new_trace_id()


class TraceIdMiddleware:
    """Bind a trace id for the request and echo it on the response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        trace_id = sanitize_trace_id(Headers(scope=scope).get(TRACE_HEADER))
        bind_trace_id(trace_id)

        async def send_with_trace(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                # The error handlers set this header themselves, on the
                # response object, before it reaches here. Theirs wins — it
                # carries the same value this middleware bound, and replacing
                # it would send the name twice.
                if not any(name == TRACE_HEADER.encode() for name, _ in headers):
                    headers.append((TRACE_HEADER.encode(), trace_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_trace)
        finally:
            # The contextvar belongs to this request. Clearing it keeps a
            # background task that outlives the request — or the next request
            # on a reused context — from logging a stale id as if it were its
            # own.
            bind_trace_id(None)


def install(app: FastAPI) -> None:
    """Wrap ``app`` so the id is bound before any route or handler runs."""
    app.add_middleware(TraceIdMiddleware)
