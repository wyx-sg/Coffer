"""The callback listener app.

One route: ``POST /seatalk/{channel}``. Verifies the SeaTalk signature with
the channel's signing secret, answers the platform's verification handshake,
and forwards every other valid event to the daemon over loopback with the
daemon token. It holds no other state and can reach nothing but the daemon.

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

    @app.post("/seatalk/{channel}", response_class=JSONResponse)
    async def seatalk_callback(channel: str, request: Request) -> Response:
        secret = signing_secrets.get(channel)
        if secret is None:
            return JSONResponse(status_code=404, content={"error": "unknown channel"})
        body = await request.body()
        signature = request.headers.get("Signature", "")
        if not verify_seatalk_signature(body, secret, signature):
            _logger.warning("callback.signature_rejected", extra={"channel": channel})
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
                f"{daemon_url}/api/v1/channels/{channel}/events",
                json=envelope,
                headers={"X-Coffer-Token": daemon_token, "X-Coffer-Actor": "system"},
            )
        except httpx.HTTPError:
            _logger.exception("callback.forward_failed", extra={"channel": channel})
            return JSONResponse(status_code=502, content={"error": "daemon unreachable"})
        if forwarded.status_code != 200:
            return JSONResponse(status_code=502, content={"error": "daemon refused"})
        return JSONResponse(status_code=200, content={"accepted": True})

    return app
