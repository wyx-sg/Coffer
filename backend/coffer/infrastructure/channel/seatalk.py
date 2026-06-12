"""SeaTalk transport: callback events in (via the listener), Open APIs out.

No SDK — token caching plus three POST endpoints. Inbound events arrive
through the daemon's events-ingest route (the callback listener forwards
them); this adapter only normalizes them, it owns no poll loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from coffer.application.channel.ports import AdapterCallbacks
from coffer.domain.channel.envelopes import (
    ApprovalClick,
    ChannelCapabilities,
    InboundMessage,
    SentMessage,
)
from coffer.domain.channel.errors import ChannelSendFailed

_logger = logging.getLogger(__name__)

_CHUNK_LIMIT = 3500  # paragraph-chunking budget, in characters
_BYTE_LIMIT = 3900  # SeaTalk caps content at 4096 BYTES; stay clear of it


def _split_to_byte_limit(chunk: str, byte_limit: int) -> list[str]:
    """Split a chunk further until each piece fits the UTF-8 byte cap.

    chunk_text counts characters, but CJK text is 3 bytes per character in
    UTF-8 — a 3500-character chunk can be ~10 KB. Halve at character
    boundaries until every piece encodes under the limit.
    """
    if len(chunk.encode("utf-8")) <= byte_limit:
        return [chunk]
    mid = len(chunk) // 2
    return _split_to_byte_limit(chunk[:mid], byte_limit) + _split_to_byte_limit(
        chunk[mid:], byte_limit
    )


_TOKEN_SLACK_SECONDS = 60
_RATE_BACKOFF = (1.0, 3.0, 9.0)


class SeaTalkAdapter:
    """One SeaTalk app/bot ↔ one channel resource."""

    def __init__(
        self,
        channel_name: str,
        app_id: str,
        app_secret: str,
        *,
        client: httpx.AsyncClient | None = None,
        base_url: str = "https://openapi.seatalk.io",
    ) -> None:
        self._name = channel_name
        self._app_id = app_id
        self._app_secret = app_secret
        self._base = base_url
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=30.0))
        self._callbacks: AdapterCallbacks | None = None
        self._token: str | None = None
        self._token_expires_at = 0.0

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            supports_edit=False,
            supports_buttons=True,
            supports_typing=True,
            max_message_chars=_CHUNK_LIMIT,
        )

    # -- lifecycle ---------------------------------------------------------

    async def start(self, callbacks: AdapterCallbacks) -> None:
        self._callbacks = callbacks

    async def stop(self) -> None:
        self._callbacks = None
        await self._client.aclose()

    # -- inbound (fed by the events-ingest route) ----------------------------

    async def handle_event(self, envelope: dict[str, Any]) -> None:
        """Normalize one verified SeaTalk event envelope and hand it to the core."""
        if self._callbacks is None:
            return
        event_type = str(envelope.get("event_type", ""))
        event = envelope.get("event")
        if not isinstance(event, dict):
            return
        if event_type == "message_from_bot_subscriber":
            message = event.get("message") or {}
            tag = str(message.get("tag", ""))
            text = ""
            if tag == "text":
                text = str((message.get("text") or {}).get("content", ""))
            await self._callbacks.on_message(
                InboundMessage(
                    channel=self._name,
                    chat_id=str(event.get("employee_code", "")),
                    sender_display=str(event.get("email", "") or event.get("seatalk_id", "")),
                    text=text,
                    platform_message_id=str(message.get("message_id", "")),
                    timestamp=datetime.fromtimestamp(
                        int(envelope.get("timestamp", 0) or 0), tz=UTC
                    ),
                )
            )
        elif event_type == "interactive_message_click":
            await self._callbacks.on_approval_click(
                ApprovalClick(
                    channel=self._name,
                    chat_id=str(event.get("employee_code", "")),
                    value=str(event.get("value", "")),
                    prompt_message_id=str(event.get("message_id", "")),
                )
            )

    # -- outbound ------------------------------------------------------------

    async def send_text(self, chat_id: str, markdown: str) -> SentMessage:
        from coffer.infrastructure.channel.render import chunk_text

        last = ""
        for chunk in chunk_text(markdown, self.capabilities.max_message_chars):
            for piece in _split_to_byte_limit(chunk, _BYTE_LIMIT):
                result = await self._send_single_chat(
                    chat_id, {"tag": "text", "text": {"format": 1, "content": piece}}
                )
                last = str(result.get("message_id", ""))
        return SentMessage(message_id=last)

    async def edit_text(self, chat_id: str, message_id: str, text: str) -> None:
        raise ChannelSendFailed(self._name, "seatalk cannot edit messages")

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        raise ChannelSendFailed(self._name, "seatalk cannot delete messages")

    async def send_typing(self, chat_id: str) -> None:
        with contextlib.suppress(Exception):
            await self._post(
                "/messaging/v2/single_chat_typing", {"employee_code": chat_id}, retries=0
            )

    async def send_approval_prompt(
        self, chat_id: str, text: str, *, allow_value: str, deny_value: str
    ) -> SentMessage:
        card = {
            "elements": [
                {"element_type": "description", "description": {"format": 2, "text": text}},
                {
                    "element_type": "button",
                    "button": {
                        "button_type": "callback",
                        "text": "✅ Approve",
                        "value": allow_value,
                    },
                },
                {
                    "element_type": "button",
                    "button": {"button_type": "callback", "text": "❌ Deny", "value": deny_value},
                },
            ]
        }
        result = await self._send_single_chat(
            chat_id, {"tag": "interactive_message", "interactive_message": card}
        )
        return SentMessage(message_id=str(result.get("message_id", "")))

    async def resolve_approval_prompt(
        self, chat_id: str, message_id: str, outcome_text: str
    ) -> None:
        # SeaTalk has no reliable message-edit API; deliver the outcome as a
        # follow-up message instead.
        await self.send_text(chat_id, outcome_text)

    # -- transport -------------------------------------------------------------

    async def _send_single_chat(self, employee_code: str, message: dict[str, Any]) -> Any:
        return await self._post(
            "/messaging/v2/single_chat",
            {"employee_code": employee_code, "message": message},
        )

    async def _ensure_token(self) -> str:
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

    async def _post(self, path: str, body: dict[str, Any], *, retries: int = 3) -> Any:
        attempt = 0
        while True:
            token = await self._ensure_token()
            try:
                response = await self._client.post(
                    f"{self._base}{path}",
                    json=body,
                    headers={"Authorization": f"Bearer {token}"},
                )
            except httpx.HTTPError as e:
                raise ChannelSendFailed(self._name, f"{path}: {type(e).__name__}") from e
            try:
                payload: Any = response.json()
            except ValueError as e:
                # A gateway returns an HTML error page, not the Open API JSON
                # envelope — json() raises a JSONDecodeError (NOT an
                # httpx.HTTPError), so surface it as the channel error contract.
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
