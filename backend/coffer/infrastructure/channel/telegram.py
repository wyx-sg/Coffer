"""Telegram transport: long polling in, Bot API methods out.

No SDK — the seven Bot API methods used here are plain POSTs. Long polling (`getUpdates`) needs
no public ingress, which is what a local-first daemon wants; the update offset is committed
only after a dispatch attempt, so a reconnect never re-delivers what the core already saw.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import pathlib
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import httpx

from coffer.application.channel.ports import AdapterCallbacks
from coffer.domain.channel.envelopes import (
    ChannelCapabilities,
    ChoiceButton,
    InboundAttachment,
    InboundCallback,
    InboundMessage,
    SentMessage,
)
from coffer.domain.channel.errors import ChannelSendFailed
from coffer.domain.channel.rich_content import ForwardedItem
from coffer.infrastructure.channel.render import chunk_text, markdown_to_telegram_html
from coffer.infrastructure.channel.telegram_media import (
    COMMANDS,
    default_media_dir,
    inline_keyboard,
    media_specs,
    upload_media,
)
from coffer.infrastructure.channel.telegram_parse import (
    addressed_and_text,
    is_group,
    prepend_context,
)

_logger = logging.getLogger(__name__)

_POLL_TIMEOUT_SECONDS = 50
_BACKOFF_LADDER = (1.0, 5.0, 30.0)
_CHUNK_LIMIT = 4000


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
        media_dir: pathlib.Path | None = None,
    ) -> None:
        self._name = channel_name
        self._base = f"{base_url}/bot{bot_token}"
        # File downloads use {base}/file/bot{token}/{path}, not {base}/bot{token}/{method}.
        self._file_base = f"{base_url}/file/bot{bot_token}"
        self._media_dir = media_dir or default_media_dir()
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, read=poll_timeout + 10.0)
        )
        self._poll_timeout = poll_timeout
        self._callbacks: AdapterCallbacks | None = None
        self._task: asyncio.Task[None] | None = None
        # Populated from getMe() in start(); stays None if that call fails.
        self._bot_id: int | None = None
        self._bot_username: str | None = None

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            supports_edit=True,
            supports_typing=True,
            max_message_chars=_CHUNK_LIMIT,
            supports_buttons=True,
            supports_media=True,
            supports_groups=True,
        )

    # -- lifecycle ---------------------------------------------------------

    async def start(self, callbacks: AdapterCallbacks) -> None:
        self._callbacks = callbacks
        with contextlib.suppress(Exception):
            await self._call("setMyCommands", commands=COMMANDS)
        with contextlib.suppress(Exception):
            me = await self._call("getMe")
            if isinstance(me, dict):
                self._bot_id = int(me["id"]) if "id" in me else None
                self._bot_username = str(me["username"]) if me.get("username") else None
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
                    "allowed_updates": ["message", "callback_query"],
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
            group = is_group(message)
            raw_text = str(message.get("text") or message.get("caption") or "")
            addressed, raw = (True, raw_text)
            if group:
                addressed, raw = addressed_and_text(
                    message, raw_text, bot_id=self._bot_id, bot_username=self._bot_username
                )
            text = prepend_context(message, raw)
            thread_id = str(message.get("message_thread_id") or "")
            sender = message.get("from") or {}
            attachments = await self._download_attachments(message)
            await self._callbacks.on_message(
                InboundMessage(
                    channel=self._name,
                    chat_id=str(message.get("chat", {}).get("id", "")),
                    sender_display=str(sender.get("first_name") or sender.get("username") or ""),
                    # A media message carries its text in ``caption``, not ``text``.
                    text=text,
                    platform_message_id=str(message.get("message_id", "")),
                    timestamp=datetime.fromtimestamp(int(message.get("date", 0)), tz=UTC),
                    sender_id=str(sender.get("id") or ""),
                    chat_kind="group" if group else "direct",
                    addressed=addressed,
                    thread_id=thread_id,
                    attachments=attachments,
                )
            )
            return
        query = update.get("callback_query")
        if isinstance(query, dict):
            await self._dispatch_callback(query)

    async def _download_attachments(self, message: dict[str, Any]) -> tuple[InboundAttachment, ...]:
        """Download each attachment on ``message`` to the media dir. Best-effort:
        a download that fails is skipped (logged), never wedging the message —
        the text/caption still drives a turn."""
        out: list[InboundAttachment] = []
        for file_id, mime, filename in media_specs(message):
            try:
                data = await self._download_file(file_id)
            except Exception:
                _logger.warning(
                    "telegram.media.download_failed",
                    extra={"channel": self._name},
                    exc_info=True,
                )
                continue
            if data is None:
                continue
            path = self._save_media(data, filename)
            out.append(InboundAttachment(path=path, mime=mime, filename=filename))
        return tuple(out)

    async def _download_file(self, file_id: str) -> bytes | None:
        """``getFile`` → download the bytes from the file endpoint."""
        info = await self._call("getFile", file_id=file_id)
        file_path = info.get("file_path") if isinstance(info, dict) else None
        if not file_path:
            return None
        response = await self._client.get(f"{self._file_base}/{file_path}")
        response.raise_for_status()
        return response.content

    def _save_media(self, data: bytes, filename: str) -> str:
        """Write bytes under the media dir with a unique name; return the path."""
        self._media_dir.mkdir(parents=True, exist_ok=True)
        suffix = pathlib.Path(filename).suffix
        path = self._media_dir / f"{uuid.uuid4().hex}{suffix}"
        path.write_bytes(data)
        return str(path)

    async def _dispatch_callback(self, query: dict[str, Any]) -> None:
        if self._callbacks is None:
            return
        sender = query.get("from") or {}
        card = query.get("message") or {}
        query_id = str(query.get("id") or "")
        if self._callbacks.on_callback is not None:
            await self._callbacks.on_callback(
                InboundCallback(
                    channel=self._name,
                    chat_id=str(card.get("chat", {}).get("id", "")),
                    sender_id=str(sender.get("id") or ""),
                    data=str(query.get("data") or ""),
                    callback_id=query_id,
                    platform_message_id=str(card.get("message_id", "")),
                )
            )
        # Dismiss the button's loading spinner (best-effort; the tap is already
        # handled, so a failed ack must not surface as a turn error).
        if query_id:
            with contextlib.suppress(Exception):
                await self._call("answerCallbackQuery", callback_query_id=query_id)

    # -- outbound ------------------------------------------------------------

    async def send_text(
        self,
        chat_id: str,
        markdown: str,
        *,
        buttons: Sequence[ChoiceButton] | None = None,
        thread_id: str = "",
        chat_kind: str = "direct",
    ) -> SentMessage:
        # chat_kind is unused: a Telegram chat_id addresses a DM or a group
        # identically, unlike SeaTalk which needs it to pick the endpoint.
        del chat_kind
        chunks = list(chunk_text(markdown, self.capabilities.max_message_chars))
        last: SentMessage | None = None
        for i, chunk in enumerate(chunks):
            # The inline keyboard rides on the final chunk so it sits under the
            # whole (possibly chunked) message.
            kb = buttons if (buttons and i == len(chunks) - 1) else None
            last = await self._send_chunk(chat_id, chunk, kb, thread_id=thread_id)
        return last if last is not None else SentMessage(message_id="")

    async def send_media(
        self,
        chat_id: str,
        path: str,
        *,
        caption: str | None = None,
        as_photo: bool = True,
        thread_id: str = "",
        chat_kind: str = "direct",
    ) -> SentMessage:
        """Upload a local file (see ``upload_media``). ``chat_kind`` is unused (a
        Telegram chat_id addresses a DM or group alike); a non-empty
        ``thread_id`` posts into that forum topic (FR-031)."""
        del chat_kind
        return await upload_media(
            self._client,
            self._base,
            self._name,
            chat_id,
            path,
            caption=caption,
            as_photo=as_photo,
            thread_id=thread_id,
        )

    async def _send_chunk(
        self,
        chat_id: str,
        chunk: str,
        buttons: Sequence[ChoiceButton] | None = None,
        *,
        thread_id: str = "",
    ) -> SentMessage:
        markup = inline_keyboard(buttons) if buttons else None
        extra: dict[str, Any] = {"reply_markup": markup} if markup is not None else {}
        if thread_id:
            extra["message_thread_id"] = int(thread_id)
        try:
            sent = await self._call(
                "sendMessage",
                chat_id=chat_id,
                text=markdown_to_telegram_html(chunk),
                parse_mode="HTML",
                **extra,
            )
        except ChannelSendFailed as e:
            # Retry as plain text only when the platform rejected formatting (400 = bad
            # entities). A transport error may mean the send got through already — retrying
            # would duplicate; a 429 needs backoff, not an instant resend.
            if not (e.api_rejected and e.status == 400):
                raise
            sent = await self._call("sendMessage", chat_id=chat_id, text=chunk, **extra)
        return SentMessage(message_id=str(sent.get("message_id", "")))

    async def edit_text(self, chat_id: str, message_id: str, text: str) -> None:
        await self._call("editMessageText", chat_id=chat_id, message_id=message_id, text=text)

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        await self._call("deleteMessage", chat_id=chat_id, message_id=message_id)

    async def send_typing(self, chat_id: str) -> None:
        await self._call("sendChatAction", chat_id=chat_id, action="typing")

    # -- context fetch (ContextFetchPort) -------------------------------------

    async def fetch_thread(
        self, chat_id: str, thread_id: str, *, limit: int = 50
    ) -> tuple[list[ForwardedItem], tuple[InboundAttachment, ...]]:
        # Bot API has no history-fetch method — a bot only ever sees updates
        # pushed to it, never past thread history. Always empty.
        return [], ()

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
