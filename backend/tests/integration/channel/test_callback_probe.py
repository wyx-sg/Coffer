"""probe_seatalk_callback: signed handshake round-trip + failure branches."""

from __future__ import annotations

import json

import httpx
import pytest

from coffer.application.channel.callback_probe import probe_seatalk_callback
from coffer.domain.channel.signing import verify_seatalk_signature

_SECRET = "sign-me"


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_ok_when_listener_echoes_signed_challenge():
    def handler(request: httpx.Request) -> httpx.Response:
        # The probe must sign the body with the real scheme and POST it.
        assert verify_seatalk_signature(
            request.content, _SECRET, request.headers.get("Signature", "")
        )
        challenge = json.loads(request.content)["event"]["seatalk_challenge"]
        return httpx.Response(200, json={"seatalk_challenge": challenge})

    async with _client(handler) as c:
        result = await probe_seatalk_callback(
            client=c, url="https://x.example.com/seatalk/st", signing_secret=_SECRET
        )
    assert result.ok is True


@pytest.mark.asyncio
async def test_fail_on_connect_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    async with _client(handler) as c:
        result = await probe_seatalk_callback(
            client=c, url="https://x.example.com/seatalk/st", signing_secret=_SECRET
        )
    assert result.ok is False
    assert "tunnel" in result.detail


@pytest.mark.asyncio
async def test_fail_on_non_200():
    async with _client(lambda r: httpx.Response(502)) as c:
        result = await probe_seatalk_callback(
            client=c, url="https://x.example.com/seatalk/st", signing_secret=_SECRET
        )
    assert result.ok is False
    assert "502" in result.detail


@pytest.mark.asyncio
async def test_fail_on_challenge_mismatch():
    async with _client(lambda r: httpx.Response(200, json={"seatalk_challenge": "nope"})) as c:
        result = await probe_seatalk_callback(
            client=c, url="https://x.example.com/seatalk/st", signing_secret=_SECRET
        )
    assert result.ok is False
    assert "challenge" in result.detail
