"""The callback-listener app (create_listener_app) over ASGI, plus the
``python -m coffer.surfaces.callback`` env-parsing contract.

The listener is driven via httpx.ASGITransport; the daemon behind it is a
stub FastAPI app mounted the same way, so the forward leg (URL, token
header, envelope body) is asserted without any real network.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from coffer.domain.channel.signing import seatalk_signature
from coffer.surfaces.callback.app import create_listener_app

_SECRET = "sec-1"


class _StubDaemon:
    """Records what the listener forwards to /api/v1/channels/{name}/events."""

    def __init__(self) -> None:
        self.received: list[tuple[str, dict[str, Any], str | None, str | None]] = []
        self.respond_status = 200
        self.app = FastAPI()
        self.app.post("/api/v1/channels/{name}/events")(self._ingest)

    async def _ingest(self, name: str, request: Request) -> JSONResponse:
        self.received.append(
            (
                name,
                await request.json(),
                request.headers.get("X-Coffer-Token"),
                request.headers.get("X-Coffer-Actor"),
            )
        )
        return JSONResponse(status_code=self.respond_status, content={"accepted": True})


def _signed(envelope: Any, secret: str = _SECRET) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(envelope).encode()
    return body, {
        "Signature": seatalk_signature(body, secret),
        "Content-Type": "application/json",
    }


@pytest.fixture
async def listener() -> AsyncIterator[tuple[httpx.AsyncClient, _StubDaemon]]:
    stub = _StubDaemon()
    daemon_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=stub.app), base_url="http://daemon"
    )
    app = create_listener_app(
        signing_secrets={"ch": _SECRET},
        daemon_url="http://daemon",
        daemon_token="tok-1",
        client=daemon_client,
    )
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://listener")
    yield client, stub
    await client.aclose()
    await daemon_client.aclose()


async def test_verification_handshake_echoes_challenge_without_forwarding(
    listener: tuple[httpx.AsyncClient, _StubDaemon],
) -> None:
    client, stub = listener
    body, headers = _signed(
        {"event_type": "event_verification", "event": {"seatalk_challenge": "ch-42"}}
    )
    r = await client.post("/seatalk/ch", content=body, headers=headers)
    assert r.status_code == 200
    assert r.json() == {"seatalk_challenge": "ch-42"}
    assert stub.received == []  # answered locally, never forwarded


@pytest.mark.acceptance(spec="009-channels", scenario="a signed seatalk event reaches the channel")
async def test_signed_event_is_forwarded_to_the_daemon_with_token(
    listener: tuple[httpx.AsyncClient, _StubDaemon],
) -> None:
    client, stub = listener
    envelope = {
        "event_type": "message_from_bot_subscriber",
        "timestamp": 1718000000,
        "event": {"employee_code": "emp-1", "message": {"tag": "text", "text": {"content": "hi"}}},
    }
    body, headers = _signed(envelope)
    r = await client.post("/seatalk/ch", content=body, headers=headers)
    assert r.status_code == 200
    assert r.json() == {"accepted": True}
    [(name, forwarded, token, actor)] = stub.received
    assert name == "ch"
    assert forwarded == envelope  # the raw envelope crosses unchanged
    assert token == "tok-1"  # daemon auth rides the forward leg
    assert actor == "system"


@pytest.mark.acceptance(spec="009-channels", scenario="a tampered seatalk event is rejected")
async def test_tampered_event_is_rejected_and_never_forwarded(
    listener: tuple[httpx.AsyncClient, _StubDaemon],
) -> None:
    client, stub = listener
    envelope = {"event_type": "message_from_bot_subscriber", "event": {"employee_code": "emp-1"}}
    body, headers = _signed(envelope)
    tampered = body.replace(b"emp-1", b"emp-2")  # body changed after signing
    r = await client.post("/seatalk/ch", content=tampered, headers=headers)
    assert r.status_code == 401
    assert r.json() == {"error": "bad signature"}

    missing = await client.post(
        "/seatalk/ch", content=body, headers={"Content-Type": "application/json"}
    )
    assert missing.status_code == 401  # no Signature header at all

    assert stub.received == []  # nothing reached the daemon


async def test_unknown_channel_is_404(listener: tuple[httpx.AsyncClient, _StubDaemon]) -> None:
    client, stub = listener
    body, headers = _signed({"event_type": "x", "event": {}}, secret="whatever")
    r = await client.post("/seatalk/nope", content=body, headers=headers)
    assert r.status_code == 404
    assert r.json() == {"error": "unknown channel"}
    assert stub.received == []


async def test_signed_but_malformed_bodies_are_400(
    listener: tuple[httpx.AsyncClient, _StubDaemon],
) -> None:
    client, stub = listener
    not_json = b"this is not json"
    r = await client.post(
        "/seatalk/ch",
        content=not_json,
        headers={"Signature": seatalk_signature(not_json, _SECRET)},
    )
    assert r.status_code == 400

    body, headers = _signed(["an", "array"])
    r2 = await client.post("/seatalk/ch", content=body, headers=headers)
    assert r2.status_code == 400
    assert stub.received == []


async def test_daemon_refusal_maps_to_502(
    listener: tuple[httpx.AsyncClient, _StubDaemon],
) -> None:
    client, stub = listener
    stub.respond_status = 409  # daemon answered, but not 200
    body, headers = _signed({"event_type": "interactive_message_click", "event": {}})
    r = await client.post("/seatalk/ch", content=body, headers=headers)
    assert r.status_code == 502
    assert r.json() == {"error": "daemon refused"}


async def test_daemon_unreachable_maps_to_502() -> None:
    def _refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    dead_client = httpx.AsyncClient(transport=httpx.MockTransport(_refuse))
    app = create_listener_app(
        signing_secrets={"ch": _SECRET},
        daemon_url="http://daemon",
        daemon_token="tok-1",
        client=dead_client,
    )
    body, headers = _signed({"event_type": "interactive_message_click", "event": {}})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://listener"
    ) as client:
        r = await client.post("/seatalk/ch", content=body, headers=headers)
    await dead_client.aclose()
    assert r.status_code == 502
    assert r.json() == {"error": "daemon unreachable"}


# -- __main__ env parsing -------------------------------------------------------


def _run_main(extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("COFFER_CB_")}
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "coffer.surfaces.callback"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_main_exits_2_when_required_env_is_missing() -> None:
    proc = _run_main({})
    assert proc.returncode == 2
    assert "bad environment" in proc.stderr


def test_main_exits_2_when_secrets_env_is_not_an_object() -> None:
    proc = _run_main(
        {
            "COFFER_CB_PORT": "1",
            "COFFER_CB_SECRETS": "[]",
            "COFFER_CB_DAEMON_URL": "http://127.0.0.1:1",
            "COFFER_CB_DAEMON_TOKEN": "t",
        }
    )
    assert proc.returncode == 2
    assert "JSON object" in proc.stderr
