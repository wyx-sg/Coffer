"""Ask a chat platform who a set of credentials belongs to.

The adapter behind ``application.channel.credential_check.CredentialProbe``:
Telegram's ``getMe`` and SeaTalk's app-access-token request. Each is one POST,
and neither stores anything or starts a channel.
"""

from __future__ import annotations

from typing import Any

import httpx

from coffer.application.channel.credential_check import CredentialProbeError, ProbedBot

_TELEGRAM = "https://api.telegram.org"
_SEATALK = "https://openapi.seatalk.io"


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        # A gateway answered with an HTML error page, not the platform's envelope.
        raise CredentialProbeError("unreachable", f"HTTP {response.status_code}") from None
    return payload if isinstance(payload, dict) else {}


class PlatformCredentialProbe:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        telegram_base: str = _TELEGRAM,
        seatalk_base: str = _SEATALK,
    ) -> None:
        self._client = client
        self._telegram_base = telegram_base
        self._seatalk_base = seatalk_base

    async def _post(self, url: str, **kwargs: Any) -> httpx.Response:
        try:
            if self._client is not None:
                return await self._client.post(url, **kwargs)
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                return await client.post(url, **kwargs)
        except httpx.HTTPError as e:
            # The class name only: the message of an httpx error carries the URL,
            # and a Telegram URL carries the token.
            raise CredentialProbeError("unreachable", type(e).__name__) from None

    async def telegram(self, bot_token: str) -> ProbedBot:
        response = await self._post(f"{self._telegram_base}/bot{bot_token}/getMe")
        payload = _json(response)
        if not payload.get("ok"):
            if response.status_code in (401, 404):
                raise CredentialProbeError("rejected", str(payload.get("description") or ""))
            raise CredentialProbeError(
                "unreachable", str(payload.get("description") or f"HTTP {response.status_code}")
            )
        me = payload.get("result")
        if not isinstance(me, dict) or not isinstance(me.get("id"), int):
            raise CredentialProbeError("unreachable", "unexpected getMe answer")
        username = me.get("username")
        first = me.get("first_name")
        return ProbedBot(
            bot_id=str(me["id"]),
            handle=str(username) if username else None,
            name=str(first) if first else None,
        )

    async def seatalk(self, app_id: str, app_secret: str) -> ProbedBot:
        response = await self._post(
            f"{self._seatalk_base}/auth/app_access_token",
            json={"app_id": app_id, "app_secret": app_secret},
        )
        payload = _json(response)
        if payload.get("code", -1) != 0 or not payload.get("app_access_token"):
            raise CredentialProbeError("rejected")
        return ProbedBot(bot_id=app_id)
