"""Telegram transport: long polling in, Bot API methods out.

No SDK — the seven Bot API methods used here are plain POSTs. Long polling
(`getUpdates`) needs no public ingress, which is what a local-first daemon
wants; the update offset is committed only after a dispatch attempt, so a
reconnect never re-delivers what the core already saw.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from coffer.application.channel.ports import AdapterCallbacks
from coffer.domain.channel.envelopes import (
    ChannelCapabilities,
    InboundMessage,
    SentMessage,
)
from coffer.domain.channel.errors import ChannelSendFailed
from coffer.infrastructure.channel.render import chunk_text, markdown_to_telegram_html

_logger = logging.getLogger(__name__)

_POLL_TIMEOUT_SECONDS = 50
_BACKOFF_LADDER = (1.0, 5.0, 30.0)
_CHUNK_LIMIT = 4000

_COMMANDS = [
    {"command": "new", "description": "Start a fresh conversation"},
    {"command": "stop", "description": "Interrupt the running turn"},
    {"command": "status", "description": "Conversation and turn state"},
    {"command": "help", "description": "List commands"},
]


class TelegramAdapter:
    """One bot account ↔ one channel resource."""

    def __init__(
        self,
        channel_name: str,
        bot_token: str,
        *,
        client: httpx.AsyncClient | None = None,
        base_url: str = "https://api.telegram.org",
        poll_timeout: int = _POLL_TIMEOUT_SECONDS,
    ) -> None:
        self._name = channel_name
        self._base = f"{base_url}/bot{bot_token}"
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, read=poll_timeout + 10.0)
        )
        self._poll_timeout = poll_timeout
        self._callbacks: AdapterCallbacks | None = None
        self._task: asyncio.Task[None] | None = None

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            supports_edit=True,
            supports_typing=True,
            max_message_chars=_CHUNK_LIMIT,
        )

    # -- lifecycle ---------------------------------------------------------

    async def start(self, callbacks: AdapterCallbacks) -> None:
        self._callbacks = callbacks
        with contextlib.suppress(Exception):
            await self._call("setMyCommands", commands=_COMMANDS)
        self._task = asyncio.create_task(self._poll_loop(), name=f"telegram-poll:{self._name}")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self._client.aclose()

    # -- inbound -------------------------------------------------------------

    async def _poll_loop(self) -> None:
        offset: int | None = None
        failures = 0
        while True:
            try:
                params: dict[str, Any] = {
                    "timeout": self._poll_timeout,
                    "allowed_updates": ["message"],
                }
                if offset is not None:
                    params["offset"] = offset
                updates = await self._call("getUpdates", **params)
                failures = 0
            except asyncio.CancelledError:
                raise
            except Exception:
                delay = _BACKOFF_LADDER[min(failures, len(_BACKOFF_LADDER) - 1)]
                failures += 1
                _logger.warning(
                    "telegram.poll.retry", extra={"channel": self._name, "delay": delay}
                )
                await asyncio.sleep(delay)
                continue
            if not isinstance(updates, list):
                _logger.warning("telegram.poll.bad_payload", extra={"channel": self._name})
                continue
            for update in updates:
                if not isinstance(update, dict) or "update_id" not in update:
                    # Malformed element: skip without touching the offset —
                    # never let one bad update kill the poll task.
                    _logger.warning("telegram.poll.bad_update", extra={"channel": self._name})
                    continue
                try:
                    await self._dispatch(update)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    _logger.exception("telegram.dispatch.failed", extra={"channel": self._name})
                # Commit only after the dispatch attempt: a crash before this
                # line re-delivers; a poison update does not wedge the loop.
                offset = int(update["update_id"]) + 1

    async def _dispatch(self, update: dict[str, Any]) -> None:
        if self._callbacks is None:
            return
        message = update.get("message")
        if isinstance(message, dict):
            sender = message.get("from") or {}
            await self._callbacks.on_message(
                InboundMessage(
                    channel=self._name,
                    chat_id=str(message.get("chat", {}).get("id", "")),
                    sender_display=str(sender.get("first_name") or sender.get("username") or ""),
                    text=str(message.get("text") or ""),
                    platform_message_id=str(message.get("message_id", "")),
                    timestamp=datetime.fromtimestamp(int(message.get("date", 0)), tz=UTC),
                    sender_id=str(sender.get("id") or ""),
                )
            )

    # -- outbound ------------------------------------------------------------

    async def send_text(self, chat_id: str, markdown: str) -> SentMessage:
        last: SentMessage | None = None
        for chunk in chunk_text(markdown, self.capabilities.max_message_chars):
            last = await self._send_chunk(chat_id, chunk)
        return last if last is not None else SentMessage(message_id="")

    async def _send_chunk(self, chat_id: str, chunk: str) -> SentMessage:
        try:
            sent = await self._call(
                "sendMessage",
                chat_id=chat_id,
                text=markdown_to_telegram_html(chunk),
                parse_mode="HTML",
            )
        except ChannelSendFailed as e:
            # Retry as plain text ONLY when the platform explicitly rejected
            # the formatted message (400 = can't parse entities). A transport
            # error may mean the first send actually got through — resending
            # would duplicate; a 429 needs backoff, not an instant resend.
            if not (e.api_rejected and e.status == 400):
                raise
            sent = await self._call("sendMessage", chat_id=chat_id, text=chunk)
        return SentMessage(message_id=str(sent.get("message_id", "")))

    async def edit_text(self, chat_id: str, message_id: str, text: str) -> None:
        await self._call("editMessageText", chat_id=chat_id, message_id=message_id, text=text)

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        await self._call("deleteMessage", chat_id=chat_id, message_id=message_id)

    async def send_typing(self, chat_id: str) -> None:
        await self._call("sendChatAction", chat_id=chat_id, action="typing")

    # -- transport -------------------------------------------------------------

    async def _call(self, method: str, **params: Any) -> Any:
        try:
            response = await self._client.post(f"{self._base}/{method}", json=params)
        except httpx.HTTPError as e:
            raise ChannelSendFailed(self._name, type(e).__name__) from e
        try:
            payload = response.json()
        except ValueError as e:
            # A gateway 502/503 returns an HTML page, not the Bot API JSON
            # envelope — json() raises (a JSONDecodeError is NOT an
            # httpx.HTTPError), so surface it as the channel error contract.
            raise ChannelSendFailed(
                self._name,
                f"{method}: non-JSON response ({response.status_code})",
                api_rejected=True,
                status=response.status_code,
            ) from e
        if not isinstance(payload, dict) or not payload.get("ok", False):
            description = ""
            if isinstance(payload, dict):
                description = str(payload.get("description", ""))
            raise ChannelSendFailed(
                self._name,
                f"{method}: {description or response.status_code}",
                api_rejected=True,
                status=response.status_code,
            )
        return payload.get("result")
