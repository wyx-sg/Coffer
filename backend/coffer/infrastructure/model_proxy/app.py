"""The model proxy's ASGI app — raw ASGI, deliberately not Starlette routing or
``BaseHTTPMiddleware``, which buffer through an anyio stream and would sit
between an upstream's SSE and the agent.

Every request, before anything else (ADR api-key-providers-are-reached-through-
a-separate-local-model-proxy, "Surface"):

- a ``Host`` that is not a loopback address on the port the request arrived on
  is refused (DNS rebinding), with no escape hatch — the daemon's
  ``COFFER_ALLOWED_HOSTS`` does not apply here;
- ANY request carrying an ``Origin`` is refused: only a browser sends one, and
  no browser page has business with this port.

Routes, everything else 404:

- ``POST /anthropic/v1/messages`` (metered), ``POST
  /anthropic/v1/messages/count_tokens``, ``GET /anthropic/v1/models`` (the
  primary member only), ``POST /openai/v1/responses`` (metered);
- ``HEAD|GET /api/hello`` and ``/anthropic/api/hello`` — Claude Code's warm-up
  probe, answered without auth;
- ``/_coffer/health``, ``/_coffer/state``, ``/_coffer/drain`` — the daemon's
  control routes, behind :data:`CONTROL_TOKEN_HEADER`.

Model routes authenticate with a per-agent local token (``Authorization:
Bearer`` or ``x-api-key``). Every secret the request presents must be the
SAME agent's token; anything else — no token, a claude.ai OAuth bearer
(``sk-ant-oat…``), a real provider key — is a 401 in the wire's own error
shape and nothing is forwarded.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import time
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError
from starlette.types import Receive, Scope, Send

from coffer.domain.model_proxy.state import (
    CONTROL_TOKEN_HEADER,
    ProxyAgent,
    ProxyState,
    token_digest,
)
from coffer.domain.usage.records import Wire
from coffer.infrastructure.model_proxy import wire as w
from coffer.infrastructure.model_proxy.members import MemberBook
from coffer.infrastructure.model_proxy.relay import Relay, RelayConfig, RelayRequest
from coffer.infrastructure.model_proxy.spool import UsageSpool
from coffer.infrastructure.net.loopback_authority import is_allowed_host

_logger = logging.getLogger(__name__)

_JSON = [(b"content-type", b"application/json")]

#: A request body larger than this is refused rather than held in memory.
MAX_BODY_BYTES = 64 * 1024 * 1024

#: ``(method, path)`` -> ``(wire, endpoint, metered, primary_only)``.
_MODEL_ROUTES: dict[tuple[str, str], tuple[Wire, str, bool, bool]] = {
    ("POST", "/anthropic/v1/messages"): (Wire.ANTHROPIC, "/v1/messages", True, False),
    ("POST", "/anthropic/v1/messages/count_tokens"): (
        Wire.ANTHROPIC,
        "/v1/messages/count_tokens",
        False,
        False,
    ),
    ("GET", "/anthropic/v1/models"): (Wire.ANTHROPIC, "/v1/models", False, True),
    ("POST", "/openai/v1/responses"): (Wire.OPENAI, "/v1/responses", True, False),
}
_HELLO_PATHS = frozenset({"/api/hello", "/anthropic/api/hello"})


def _wire_of(path: str) -> Wire | None:
    if path.startswith("/anthropic/"):
        return Wire.ANTHROPIC
    if path.startswith("/openai/"):
        return Wire.OPENAI
    return None


def _port_of(scope: Scope) -> int:
    server = scope.get("server")
    if server and len(server) >= 2 and isinstance(server[1], int):
        return int(server[1])
    return -1  # no transport address: nothing can match, so the Host check refuses


class ModelProxyApp:
    """The proxy process's whole HTTP surface."""

    def __init__(
        self,
        *,
        control_token: str,
        version: str,
        started_at: str,
        spool: UsageSpool | None = None,
        relay_config: RelayConfig | None = None,
        on_drained: Callable[[], None] | None = None,
    ) -> None:
        self._control_token = control_token
        self.version = version
        self.started_at = started_at
        self.pid = os.getpid()
        self.spool = spool
        self.book = MemberBook()
        self.relay = Relay(self.book, spool, relay_config)
        self.state = ProxyState()
        self.inflight = 0
        self.draining = False
        self.on_drained = on_drained

    # --- ASGI --------------------------------------------------------------------

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self._lifespan(receive, send)
            return
        if scope["type"] != "http":
            return  # websockets are not served: the transport closes it
        path: str = scope.get("path", "")
        method: str = scope.get("method", "GET")
        raw: w.RawHeaders = list(scope.get("headers", []))
        wire = _wire_of(path)
        if not is_allowed_host(w.header(raw, b"host"), _port_of(scope)):
            await _reply(
                send,
                403,
                wire,
                "This proxy only answers requests addressed to "
                "127.0.0.1 or localhost on its own port.",
                "permission_error",
            )
            return
        if w.header(raw, b"origin") is not None:
            await _reply(
                send,
                403,
                wire,
                "This proxy does not accept requests from web pages.",
                "permission_error",
            )
            return
        if path in _HELLO_PATHS and method in ("GET", "HEAD"):
            await _send(send, 200, _JSON, b"" if method == "HEAD" else b'{"ok":true}')
            return
        if path.startswith("/_coffer/"):
            await self._control(scope, receive, send, method, path, raw)
            return
        spec = _MODEL_ROUTES.get((method, path))
        if spec is None:
            await _reply(send, 404, wire, f"No such route: {method} {path}", "not_found_error")
            return
        await self._model(scope, receive, send, raw, spec)

    async def _lifespan(self, receive: Receive, send: Send) -> None:
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                if self.spool is not None:
                    await self.spool.start()
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await self.relay.aclose()
                if self.spool is not None:
                    await self.spool.close()
                await send({"type": "lifespan.shutdown.complete"})
                return

    # --- model routes ----------------------------------------------------------------

    def authenticate(self, raw: w.RawHeaders) -> ProxyAgent | None:
        """The agent whose token every presented secret is, else None."""
        presented: list[str] = []
        for name, value in raw:
            lowered = name.lower()
            if lowered == b"x-api-key":
                presented.append(value.decode("latin-1").strip())
            elif lowered == b"authorization":
                scheme, _, token = value.decode("latin-1").partition(" ")
                presented.append(token.strip() if scheme.lower() == "bearer" else "")
        if not presented:
            return None
        found: ProxyAgent | None = None
        for token in presented:
            digest = token_digest(token)
            match: ProxyAgent | None = None
            for agent in self.state.agents:  # full loop: no early exit on a match
                if hmac.compare_digest(digest, agent.token_sha256):
                    match = agent
            if match is None or (found is not None and found.agent_uid != match.agent_uid):
                return None
            found = match
        return found

    async def _model(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        raw: w.RawHeaders,
        spec: tuple[Wire, str, bool, bool],
    ) -> None:
        wire, endpoint, metered, primary_only = spec
        agent = self.authenticate(raw)
        if agent is None:
            await _reply(
                send,
                401,
                wire,
                "Coffer's model proxy accepts only this agent's local proxy token.",
                "authentication_error",
            )
            return
        if self.draining:
            await _reply(
                send,
                503,
                wire,
                "Coffer's model proxy is restarting; retry.",
                "overloaded_error" if wire is Wire.ANTHROPIC else "api_error",
            )
            return
        route = next(
            (r for r in self.state.routes if r.agent_uid == agent.agent_uid and r.wire is wire),
            None,
        )
        if route is None or not route.members:
            await _reply(
                send,
                503,
                wire,
                "No API-key connection is active for this agent in Coffer.",
                "api_error",
            )
            return
        self.inflight += 1
        try:
            body = await _read_body(receive, MAX_BODY_BYTES)
            if body is None:
                await _reply(send, 413, wire, "Request body too large.", "request_too_large")
                return
            request = RelayRequest(
                wire=wire,
                endpoint=endpoint,
                method=scope["method"],
                query=scope.get("query_string", b""),
                headers=raw,
                body=body,
                agent=agent,
                route=route,
                metered=metered,
                primary_only=primary_only,
            )
            await self.relay.serve(request, receive, send)
        finally:
            self.inflight -= 1
            self._maybe_drained()

    # --- control routes ----------------------------------------------------------------

    def _control_ok(self, raw: w.RawHeaders) -> bool:
        given = w.header(raw, CONTROL_TOKEN_HEADER.encode()) or ""
        return hmac.compare_digest(given.encode(), self._control_token.encode())

    def health(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "pid": self.pid,
            "revision": self.state.revision,
            "inflight": self.inflight,
            "started_at": self.started_at,
            "draining": self.draining,
        }

    def replace_state(self, state: ProxyState) -> None:
        """Adopt a pushed state wholesale; a member whose key changed starts clean."""
        self.state = state
        self.book.reconcile(m for r in state.routes for m in r.members)

    async def _control(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        method: str,
        path: str,
        raw: w.RawHeaders,
    ) -> None:
        if not self._control_ok(raw):
            await _reply(send, 401, None, "Missing or wrong control token.", "unauthorized")
            return
        if method == "GET" and path == "/_coffer/health":
            await _send(send, 200, _JSON, json.dumps(self.health()).encode())
        elif method == "PUT" and path == "/_coffer/state":
            body = await _read_body(receive, MAX_BODY_BYTES) or b""
            try:
                state = ProxyState.model_validate_json(body)
            except ValidationError as exc:
                await _reply(
                    send,
                    400,
                    None,
                    f"Invalid state: {exc.error_count()} error(s).",
                    "invalid_request",
                )
                return
            self.replace_state(state)
            _logger.info(
                "model_proxy.state_replaced revision=%s agents=%s routes=%s",
                state.revision,
                len(state.agents),
                len(state.routes),
            )
            await _send(send, 200, _JSON, json.dumps({"revision": state.revision}).encode())
        elif method == "POST" and path == "/_coffer/drain":
            self.draining = True
            _logger.info("model_proxy.draining inflight=%s", self.inflight)
            await _send(send, 202, _JSON, json.dumps(self.health()).encode())
            self._maybe_drained()
        else:
            await _reply(send, 404, None, f"No such route: {method} {path}", "not_found_error")

    def _maybe_drained(self) -> None:
        if self.draining and self.inflight == 0 and self.on_drained is not None:
            callback, self.on_drained = self.on_drained, None
            callback()


async def _read_body(receive: Receive, cap: int) -> bytes | None:
    """The whole request body, or None past ``cap``. Retrying on another member
    needs it whole, and it is forwarded exactly as read."""
    chunks: list[bytes] = []
    size = 0
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            break
        chunk = message.get("body", b"")
        size += len(chunk)
        if size > cap:
            return None
        chunks.append(chunk)
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


async def _send(send: Send, status: int, headers: w.RawHeaders, body: bytes) -> None:
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body, "more_body": False})


async def _reply(send: Send, status: int, wire: Wire | None, message: str, kind: str) -> None:
    await _send(send, status, _JSON, w.error_body(wire, message, kind))


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


__all__ = ["MAX_BODY_BYTES", "ModelProxyApp", "now_iso"]
