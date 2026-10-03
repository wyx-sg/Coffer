"""The platform probe over a mocked transport: Telegram getMe and SeaTalk's
app-access-token request, and what each refusal maps to."""

from __future__ import annotations

import httpx
import pytest

from coffer.application.channel.credential_check import CredentialProbeError
from coffer.infrastructure.channel.credential_probe import PlatformCredentialProbe


def _probe(handler: httpx.MockTransport) -> PlatformCredentialProbe:
    return PlatformCredentialProbe(client=httpx.AsyncClient(transport=handler))


async def test_telegram_get_me_names_the_bot() -> None:
    seen: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(
            200, json={"ok": True, "result": {"id": 7, "username": "a_bot", "first_name": "A"}}
        )

    bot = await _probe(httpx.MockTransport(handle)).telegram("tok")
    assert seen == ["https://api.telegram.org/bottok/getMe"]
    assert (bot.bot_id, bot.handle, bot.name) == ("7", "a_bot", "A")


async def test_telegram_401_is_a_rejection_with_the_description() -> None:
    transport = httpx.MockTransport(
        lambda r: httpx.Response(401, json={"ok": False, "description": "Unauthorized"})
    )
    with pytest.raises(CredentialProbeError) as e:
        await _probe(transport).telegram("tok")
    assert (e.value.reason, e.value.detail) == ("rejected", "Unauthorized")


async def test_telegram_gateway_html_is_unreachable_not_rejected() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(502, text="<html>bad gateway</html>"))
    with pytest.raises(CredentialProbeError) as e:
        await _probe(transport).telegram("tok")
    assert e.value.reason == "unreachable"


async def test_transport_failure_does_not_leak_the_token() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("cannot reach https://api.telegram.org/botSECRET/getMe")

    with pytest.raises(CredentialProbeError) as e:
        await _probe(httpx.MockTransport(boom)).telegram("SECRET")
    assert e.value.reason == "unreachable"
    assert "SECRET" not in str(e.value)


async def test_seatalk_token_request_proves_the_secret() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        ok = b'"app_secret":"good"' in request.content.replace(b" ", b"")
        return httpx.Response(
            200, json={"code": 0, "app_access_token": "t"} if ok else {"code": 100}
        )

    probe = _probe(httpx.MockTransport(handle))
    assert (await probe.seatalk("9402", "good")).bot_id == "9402"
    with pytest.raises(CredentialProbeError) as e:
        await probe.seatalk("9402", "bad")
    assert e.value.reason == "rejected"
