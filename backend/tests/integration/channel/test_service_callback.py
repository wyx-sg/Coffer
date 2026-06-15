"""ChannelService.status public URL composition + test_callback branches."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx

from coffer.application.channel.pairing import PairingManager
from coffer.application.channel.service import ChannelService
from coffer.domain.channel.signing import verify_seatalk_signature
from coffer.domain.resource import Resource, ResourceRef


class _Resources:
    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config

    async def get(self, ref: ResourceRef) -> Resource:
        now = datetime(2026, 1, 1, tzinfo=UTC)
        return Resource(
            id=1,
            kind=ref.kind,
            name=ref.name,
            description=None,
            config=self._config,
            enabled=True,
            created_at=now,
            updated_at=now,
        )


class _Peers:
    async def get(self, resource_id: int) -> None:
        return None


class _Runtime:
    listener_port = 8787
    listener_running = True

    def is_running(self, name: str) -> bool:
        return False

    def tunnel_running(self, name: str) -> bool:
        return False


def _seatalk_config(public_base_url: str | None) -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "channel_type": "seatalk",
        "app_id": "app-1",
        "app_secret_ref": "channel/st/app-secret",
        "signing_secret_ref": "channel/st/signing-secret",
    }
    if public_base_url is not None:
        cfg["public_base_url"] = public_base_url
    return cfg


def _service(
    config: dict[str, Any], *, http_client: httpx.AsyncClient | None = None
) -> ChannelService:
    async def materialize(refs: dict[str, str]) -> dict[str, str]:
        return dict.fromkeys(refs, "the-signing-secret")

    return ChannelService(
        resources=_Resources(config),  # type: ignore[arg-type]
        peers=_Peers(),  # type: ignore[arg-type]
        pairing=PairingManager(),
        runtime=_Runtime(),  # type: ignore[arg-type]
        audit=None,  # type: ignore[arg-type]
        materialize=materialize,
        http_client=http_client,
    )


async def test_status_composes_public_callback_url():
    status = await _service(_seatalk_config("https://x.trycloudflare.com")).status("st")
    assert status.callback is not None
    assert status.callback.public_base_url == "https://x.trycloudflare.com"
    assert status.callback.public_callback_url == "https://x.trycloudflare.com/seatalk/st"


async def test_status_public_callback_url_none_when_base_unset():
    status = await _service(_seatalk_config(None)).status("st")
    assert status.callback is not None
    assert status.callback.public_callback_url is None


async def test_test_callback_ok_when_signed_challenge_echoes():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://x.trycloudflare.com/seatalk/st"
        assert verify_seatalk_signature(
            request.content, "the-signing-secret", request.headers.get("Signature", "")
        )
        challenge = json.loads(request.content)["event"]["seatalk_challenge"]
        return httpx.Response(200, json={"seatalk_challenge": challenge})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await _service(
            _seatalk_config("https://x.trycloudflare.com"), http_client=client
        ).test_callback("st")
    assert result.ok is True


async def test_test_callback_requires_public_base_url():
    result = await _service(_seatalk_config(None), http_client=httpx.AsyncClient()).test_callback(
        "st"
    )
    assert result.ok is False
    assert "base url" in result.detail.lower()


async def test_test_callback_rejects_non_seatalk():
    result = await _service(
        {"channel_type": "telegram", "bot_token_ref": "channel/tg/bot"},
        http_client=httpx.AsyncClient(),
    ).test_callback("tg")
    assert result.ok is False
    assert "SeaTalk" in result.detail
