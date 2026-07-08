"""SeaTalk Open API transport: app-access-token caching and the one
authenticated request path (token refresh on code 100, 429/rate-limit backoff,
non-JSON gateway handling).

Split out of ``seatalk.py`` (mirroring ``seatalk_parse.py`` / ``seatalk_media.py``)
so the adapter module holds only the event-normalization and send-routing
surface. The adapter keeps thin ``_ensure_token``/``_post``/``_get`` delegators
over one :class:`SeaTalkTransport` instance, preserving every call site (and
test seam) unchanged.
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
            raise ChannelSendFailed(self._name, f"{path}: code={code} http={response.status_code}")
