"""A send whose connection never opened is resent: the request was not sent, so a
resend cannot duplicate it (spec channels "Render replies by the adapter's
declared capabilities"). A failure after the request went out is not resent."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from coffer.domain.channel.errors import ChannelSendFailed
from coffer.infrastructure.channel import seatalk_transport, telegram_transport
from coffer.infrastructure.channel.seatalk_transport import SeaTalkTransport


@pytest.fixture(autouse=True)
def _no_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    async def instant(_delay: float) -> None:
        return None

    monkeypatch.setattr(telegram_transport.asyncio, "sleep", instant)
    monkeypatch.setattr(seatalk_transport.asyncio, "sleep", instant)


def _flaky(fail: int, error: type[Exception], ok: dict[str, Any]) -> tuple[Any, list[str]]:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path.endswith("app_access_token"):
            return httpx.Response(200, json={"code": 0, "app_access_token": "t", "expire": 7200})
        if len([p for p in seen if not p.endswith("app_access_token")]) <= fail:
            raise error("down", request=request)
        return httpx.Response(200, json=ok)

    return httpx.MockTransport(handler), seen


@pytest.mark.acceptance(spec="channels", scenario="a send whose connection never opened is resent")
async def test_telegram_resends_a_call_that_never_connected() -> None:
    transport, seen = _flaky(2, httpx.ConnectError, {"ok": True, "result": {"message_id": 7}})
    async with httpx.AsyncClient(transport=transport) as client:
        result = await telegram_transport.call(client, "https://t", "tg", "sendMessage", text="hi")

    assert result == {"message_id": 7}
    assert len(seen) == 3


async def test_telegram_gives_up_after_the_backoff() -> None:
    transport, seen = _flaky(9, httpx.ConnectTimeout, {"ok": True, "result": {}})
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ChannelSendFailed):
            await telegram_transport.call(client, "https://t", "tg", "sendMessage", text="hi")

    assert len(seen) == 3


async def test_telegram_does_not_resend_after_the_request_went_out() -> None:
    # A read timeout may mean the message was delivered: resending could duplicate it.
    transport, seen = _flaky(1, httpx.ReadTimeout, {"ok": True, "result": {}})
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ChannelSendFailed):
            await telegram_transport.call(client, "https://t", "tg", "sendMessage", text="hi")

    assert len(seen) == 1


async def test_seatalk_resends_a_call_that_never_connected() -> None:
    transport, seen = _flaky(1, httpx.ConnectError, {"code": 0, "message_id": "m1"})
    async with httpx.AsyncClient(transport=transport) as client:
        st = SeaTalkTransport("st", "app", "secret", "https://s", client)
        result = await st.request("POST", "/messaging/v2/single_chat", json={})

    assert result["message_id"] == "m1"
    assert [p for p in seen if not p.endswith("app_access_token")] == [
        "/messaging/v2/single_chat",
        "/messaging/v2/single_chat",
    ]


async def test_seatalk_does_not_resend_after_the_request_went_out() -> None:
    transport, seen = _flaky(1, httpx.ReadTimeout, {"code": 0})
    async with httpx.AsyncClient(transport=transport) as client:
        st = SeaTalkTransport("st", "app", "secret", "https://s", client)
        with pytest.raises(ChannelSendFailed):
            await st.request("POST", "/messaging/v2/single_chat", json={})

    assert [p for p in seen if not p.endswith("app_access_token")] == ["/messaging/v2/single_chat"]
