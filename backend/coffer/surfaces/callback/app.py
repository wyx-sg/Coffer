"""The callback listener app.

One route: ``POST /seatalk/{channel_uid}``. Verifies the SeaTalk signature
with the channel's signing secret, answers the platform's verification
handshake, and forwards every other valid event to the daemon over loopback
with the daemon token. It holds no other state and can reach nothing but the
daemon.

The path segment is the channel's **uid**, not its name. This URL is registered
by hand on SeaTalk's platform, which makes it the worst possible place for a
mutable label: keyed by the name, renaming a channel severed inbound messages
with no error anywhere — the channel simply stopped receiving
(ADR resource-identity-is-an-immutable-uid). Keyed by the uid it survives every
rename. The one-time cost is that upgrading invalidates an already-registered
URL, so the owner re-registers once; the current URL is on the channel's status,
its detail page (with a copy button) and the CLI's ``register:`` line.

The user points a tunnel (cloudflared/ngrok) at this listener's port; the
daemon itself stays loopback-only.
"""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from coffer.domain.channel.signing import verify_seatalk_signature

_logger = logging.getLogger(__name__)

_FORWARD_TIMEOUT_SECONDS = 4.0  # SeaTalk expects our 200 within 5 s

# A SeaTalk event envelope is a few KB; nothing near this size is one. The
# listener sits behind a public tunnel, so a body is refused BEFORE it is
# buffered — by Content-Length when declared, else by size as it streams —
# rather than read whole into memory and only then found unsigned.
_MAX_BODY_BYTES = 1024 * 1024


async def _read_body(request: Request) -> bytes | None:
    """The request body, or ``None`` once it is known to exceed the cap.

    A declared ``Content-Length`` over the cap is refused without reading a
    byte. Without one (a chunked body), the stream is consumed only up to the
    first chunk that carries the total past the cap.
    """
    declared = request.headers.get("content-length")
    if declared is not None:
        with contextlib.suppress(ValueError):
            if int(declared) > _MAX_BODY_BYTES:
                return None
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > _MAX_BODY_BYTES:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


def create_listener_app(
    *,
    signing_secrets: dict[str, str],
    daemon_url: str,
    daemon_token: str,
    client: httpx.AsyncClient | None = None,
) -> FastAPI:
    http = client or httpx.AsyncClient(timeout=_FORWARD_TIMEOUT_SECONDS)

    @contextlib.asynccontextmanager
    async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await http.aclose()

    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None, lifespan=_lifespan)

    @app.post("/seatalk/{channel_uid}", response_class=JSONResponse)
    async def seatalk_callback(channel_uid: str, request: Request) -> Response:
        secret = signing_secrets.get(channel_uid)
        if secret is None:
            return JSONResponse(status_code=404, content={"error": "unknown channel"})
        body = await _read_body(request)
        if body is None:
            _logger.warning("callback.body_too_large", extra={"channel_uid": channel_uid})
            return JSONResponse(status_code=413, content={"error": "body too large"})
        signature = request.headers.get("Signature", "")
        if not verify_seatalk_signature(body, secret, signature):
            _logger.warning("callback.signature_rejected", extra={"channel_uid": channel_uid})
            return JSONResponse(status_code=401, content={"error": "bad signature"})
        try:
            envelope: Any = json.loads(body)
        except ValueError:
            return JSONResponse(status_code=400, content={"error": "not json"})
        if not isinstance(envelope, dict):
            return JSONResponse(status_code=400, content={"error": "not an object"})
        if envelope.get("event_type") == "event_verification":
            challenge = (envelope.get("event") or {}).get("seatalk_challenge", "")
            return JSONResponse(status_code=200, content={"seatalk_challenge": challenge})
        try:
            forwarded = await http.post(
                f"{daemon_url}/api/v1/channels/{channel_uid}/events",
                json=envelope,
                headers={"X-Coffer-Token": daemon_token, "X-Coffer-Actor": "system"},
            )
        except httpx.HTTPError:
            _logger.exception("callback.forward_failed", extra={"channel_uid": channel_uid})
            return JSONResponse(status_code=502, content={"error": "daemon unreachable"})
        if forwarded.status_code != 200:
            return JSONResponse(status_code=502, content={"error": "daemon refused"})
        return JSONResponse(status_code=200, content={"accepted": True})

    return app
