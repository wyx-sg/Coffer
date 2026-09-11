"""SeaTalk Open API transport: app-access-token caching, the one authenticated
request path (token refresh on code 100, 429/rate-limit backoff, non-JSON
gateway handling), and the single/group send shapes that path is called with.

Split out of ``seatalk.py`` (mirroring ``seatalk_parse.py`` / ``seatalk_media.py``)
so the adapter module holds only the event-normalization and send-routing
surface. The adapter holds one :class:`SeaTalkTransport` instance and reaches
it directly for the token and the send seam, keeping only the thin ``_post`` /
``_get`` delegators the remaining call sites (and their test seams) use.

Which endpoint a chat_kind maps to lives HERE rather than in the adapter: every
SeaTalk surface comes in a single-chat/group-chat pair keyed on the same
``chat_kind``, so one module owning both halves keeps the pairing visible.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from coffer.domain.channel.errors import ChannelSendFailed

_logger = logging.getLogger(__name__)

_TOKEN_SLACK_SECONDS = 60
_RATE_BACKOFF = (1.0, 3.0, 9.0)


def _detail(payload: Any) -> str:
    """The platform's own words about a rejection, ready to append to an error.

    A bare ``code=102`` says a request was refused but not what about it was
    wrong, and that number covers everything from an over-long card to a
    malformed body — two real failures we chased separately because the
    envelope's message never left this function. SeaTalk spells the reason out
    under one of several key names depending on the endpoint, so try each and
    fall back to the whole envelope minus the fields already reported.
    """
    if not isinstance(payload, dict):
        return ""
    for key in ("message", "msg", "error_msg", "error_message", "error", "detail"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return f" {key}={value.strip()!r}"
    rest = {k: v for k, v in payload.items() if k not in ("code", "request_id")}
    return f" payload={rest!r}" if rest else ""


class SeaTalkTransport:
    """Token caching + one authenticated Open API call for one channel."""

    def __init__(
        self, name: str, app_id: str, app_secret: str, base_url: str, client: httpx.AsyncClient
    ) -> None:
        self._name = name
        self._app_id = app_id
        self._app_secret = app_secret
        self._base = base_url
        self._client = client
        self._token: str | None = None
        self._token_expires_at = 0.0

    async def ensure_token(self) -> str:
        if self._token is not None and time.monotonic() < self._token_expires_at:
            return self._token
        try:
            response = await self._client.post(
                f"{self._base}/auth/app_access_token",
                json={"app_id": self._app_id, "app_secret": self._app_secret},
            )
        except httpx.HTTPError as e:
            raise ChannelSendFailed(self._name, f"token: {type(e).__name__}") from e
        try:
            payload = response.json()
        except ValueError as e:
            # A gateway returns an HTML error page, not the Open API JSON
            # envelope — json() raises a JSONDecodeError (NOT an
            # httpx.HTTPError), so surface it as the channel error contract.
            raise ChannelSendFailed(
                self._name, f"token: non-JSON response ({response.status_code})"
            ) from e
        if not isinstance(payload, dict) or payload.get("code", -1) != 0:
            raise ChannelSendFailed(self._name, "token request rejected")
        token = str(payload.get("app_access_token", ""))
        if not token:
            raise ChannelSendFailed(self._name, "token response missing app_access_token")
        expire = float(payload.get("expire", 7200) or 7200)
        ttl = max(expire - time.time(), 60.0) if expire > 1e9 else expire
        self._token = token
        self._token_expires_at = time.monotonic() + ttl - _TOKEN_SLACK_SECONDS
        return token

    # -- endpoint shapes ------------------------------------------------------

    async def send(
        self, chat_id: str, message: dict[str, Any], thread_id: str, chat_kind: str
    ) -> Any:
        """Route one already-built ``message`` payload to the group or
        single-chat endpoint, so every caller (text chunks, cards, media)
        shares one routing decision.

        ``thread_id`` goes INSIDE the message body on BOTH endpoints (FR-026):
        verified live that a top-level thread_id is ignored (the reply falls to
        the group main chat), while ``message.thread_id`` threads it and roots
        a new thread when none exists yet.
        """
        if thread_id:
            message = {**message, "thread_id": thread_id}
        if chat_kind == "group":
            return await self.request(
                "POST",
                "/messaging/v2/group_chat",
                json={"group_id": chat_id, "message": message},
            )
        return await self.request(
            "POST",
            "/messaging/v2/single_chat",
            json={"employee_code": chat_id, "message": message},
        )

    # -- the one authenticated call -------------------------------------------

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        retries: int = 3,
    ) -> Any:
        """One authenticated call with the shared token-refresh / rate-limit /
        non-JSON handling — POST carries a JSON body, GET query params."""
        attempt = 0
        while True:
            token = await self.ensure_token()
            try:
                response = await self._client.request(
                    method,
                    f"{self._base}{path}",
                    json=json,
                    params=params,
                    headers={"Authorization": f"Bearer {token}"},
                )
            except httpx.HTTPError as e:
                raise ChannelSendFailed(self._name, f"{path}: {type(e).__name__}") from e
            try:
                payload: Any = response.json()
            except ValueError as e:
                # A gateway HTML error page, not the Open API JSON envelope —
                # json() raises JSONDecodeError (not httpx.HTTPError); surface it
                # as the channel error contract.
                raise ChannelSendFailed(
                    self._name, f"{path}: non-JSON response ({response.status_code})"
                ) from e
            code = payload.get("code", -1) if isinstance(payload, dict) else -1
            if response.status_code == 200 and code == 0:
                return payload
            if code == 100:  # expired token — refresh and retry once
                self._token = None
                if attempt < max(retries, 1):
                    attempt += 1
                    continue
            rate_limited = response.status_code == 429 or code == 101
            if rate_limited and attempt < retries:
                delay = _RATE_BACKOFF[min(attempt, len(_RATE_BACKOFF) - 1)]
                attempt += 1
                _logger.warning(
                    "seatalk.rate_limited", extra={"channel": self._name, "delay": delay}
                )
                await asyncio.sleep(delay)
                continue
            raise ChannelSendFailed(
                self._name,
                f"{path}: code={code} http={response.status_code}{_detail(payload)}",
                api_rejected=True,
                status=response.status_code,
            )
