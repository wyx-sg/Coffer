"""Telegram transport: long polling in, Bot API methods out.

No SDK — the Bot API methods used here are plain POSTs. Long polling (`getUpdates`) needs no
public ingress; the offset commits only after a dispatch attempt, so a reconnect never replays.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import pathlib
from collections.abc import Sequence
from typing import Any

import httpx

from coffer.application.channel.ports import AdapterCallbacks
from coffer.domain.channel.dedup import SeenIds
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
from coffer.infrastructure.channel.live_text import TelegramLiveText
from coffer.infrastructure.channel.render import chunk_text, markdown_to_telegram_html
from coffer.infrastructure.channel.telegram_album import AlbumBuffer
from coffer.infrastructure.channel.telegram_cards import edit_card
from coffer.infrastructure.channel.telegram_media import (
    COMMANDS,
    default_media_dir,
    download_attachments,
    inline_keyboard,
    upload_media,
)
from coffer.infrastructure.channel.telegram_parse import (
    build_inbound_message,
    is_group,
    thread_target,
)
from coffer.infrastructure.channel.telegram_transport import call

_logger = logging.getLogger(__name__)

_POLL_TIMEOUT_SECONDS = 50
_BACKOFF_LADDER = (1.0, 5.0, 30.0)
_CHUNK_LIMIT = 4000
# FR-038: how long to wait for more album items sharing a media_group_id before
# flushing them as one turn. Small — the items arrive back-to-back.
_ALBUM_DEBOUNCE_SECONDS = 1.0


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
        self._seen = SeenIds()  # FR-039: drop a redelivered update
        # FR-038: debounce album items sharing a media_group_id into one turn.
        self._albums = AlbumBuffer(_ALBUM_DEBOUNCE_SECONDS, self._flush_album)
        self._task: asyncio.Task[None] | None = None
        # Populated from getMe() in start(); stays None if that call fails.
        self._bot_id: int | None = None
        self._bot_username: str | None = None

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            supports_edit=True,
            supports_live_text=True,  # FR-037: the edit IS its live surface
            supports_typing=True,
            max_message_chars=_CHUNK_LIMIT,
            supports_buttons=True,
            supports_card_update=True,  # editMessageText rewrites text + keyboard
            supports_media=True,
            supports_groups=True,
            supports_reactions=True,
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
        # FR-038: drop pending album timers/flush tasks so none leak past stop.
        self._albums.cancel_all()
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
                if not isinstance(updates, list):
                    # A failure too: the old no-delay retry here spun the event loop.
                    raise ChannelSendFailed(self._name, "getUpdates: non-list result")
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
                # Commit only after dispatch: a crash re-delivers; no poison-update wedge.
                offset = int(update["update_id"]) + 1

    async def _dispatch(self, update: dict[str, Any]) -> None:
        if self._callbacks is None:
            return
        # FR-039: the poll offset normally prevents replays, but a reconnect race
        # can re-deliver — drop an already-seen update_id (covers messages + taps).
        update_id = str(update.get("update_id", ""))
        if update_id and not self._seen.add(update_id):
            return
        message = update.get("message")
        if isinstance(message, dict):
            attachments = await self._download_attachments(message)
            media_group_id = message.get("media_group_id")
            if media_group_id:
                # FR-038: an album arrives as separate updates sharing a media_group_id
                # — buffer them and flush ONE turn (FR-039 dedup still runs per-update).
                self._albums.add(str(media_group_id), message, attachments)
                return
            await self._callbacks.on_message(self._build_inbound(message, attachments))
            return
        query = update.get("callback_query")
        if isinstance(query, dict):
            await self._dispatch_callback(query)

    def _build_inbound(
        self, message: dict[str, Any], attachments: tuple[InboundAttachment, ...]
    ) -> InboundMessage:
        return build_inbound_message(
            message,
            attachments,
            channel=self._name,
            bot_id=self._bot_id,
            bot_username=self._bot_username,
        )

    async def _flush_album(
        self, message: dict[str, Any], attachments: tuple[InboundAttachment, ...]
    ) -> None:
        """FR-038: emit ONE InboundMessage for a debounced album — all its
        attachments and the caption from whichever item carried it."""
        if self._callbacks is None:
            return
        await self._callbacks.on_message(self._build_inbound(message, attachments))

    async def _download_attachments(self, message: dict[str, Any]) -> tuple[InboundAttachment, ...]:
        return await download_attachments(
            self._client, self._call, self._file_base, self._media_dir, self._name, message
        )

    async def _dispatch_callback(self, query: dict[str, Any]) -> None:
        if self._callbacks is None:
            return
        sender = query.get("from") or {}
        card = query.get("message") or {}
        query_id = str(query.get("id") or "")
        # A card tapped in a (super)group replies back into that group/thread, not a
        # DM — derive chat_kind/thread_id from the card's own message (FR-034).
        group = is_group(card)
        if self._callbacks.on_callback is not None:
            await self._callbacks.on_callback(
                InboundCallback(
                    channel=self._name,
                    chat_id=str(card.get("chat", {}).get("id", "")),
                    sender_id=str(sender.get("id") or ""),
                    data=str(query.get("data") or ""),
                    callback_id=query_id,
                    platform_message_id=str(card.get("message_id", "")),
                    chat_kind="group" if group else "direct",
                    thread_id=str(card.get("message_thread_id") or ""),
                )
            )
        # Dismiss the button's loading spinner (best-effort; the tap is already handled).
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
        title: str = "",
        thread_id: str = "",
        chat_kind: str = "direct",
    ) -> SentMessage:
        # chat_kind is unused: a Telegram chat_id addresses a DM and a group alike.
        del chat_kind
        # Telegram has no card title element — an inline keyboard hangs off an
        # ordinary message — so the title becomes the body's first line in bold
        # rather than being dropped. Same information, the platform's own shape.
        if title and buttons:
            markdown = f"**{title}**\n{markdown}"
        chunks = list(chunk_text(markdown, self.capabilities.max_message_chars))
        last: SentMessage | None = None
        for i, chunk in enumerate(chunks):
            # The inline keyboard rides on the final chunk so it sits under the
            # whole (possibly chunked) message.
            kb = buttons if (buttons and i == len(chunks) - 1) else None
            last = await self._send_chunk(chat_id, chunk, kb, thread_id=thread_id)
        return last if last is not None else SentMessage(message_id="")

    async def update_card(
        self,
        chat_id: str,
        message_id: str,
        markdown: str,
        buttons: Sequence[ChoiceButton],
        *,
        title: str = "",
        chat_kind: str = "direct",
    ) -> None:
        del chat_kind  # a Telegram chat_id addresses a DM and a group alike
        await edit_card(self._call, chat_id, message_id, markdown, buttons, title=title)

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
        """Upload a local file (see ``upload_media``). ``chat_kind`` is unused (a DM
        and group share one chat_id); a non-empty ``thread_id`` posts to that topic."""
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

    async def open_live_text(
        self, chat_id: str, *, thread_id: str = "", chat_kind: str = "direct"
    ) -> TelegramLiveText:
        """FR-037: Telegram's live surface is one message it keeps editing."""
        del chat_kind  # a Telegram chat_id addresses a DM and a group alike
        return TelegramLiveText(self._call, chat_id, thread_id=thread_id)

    async def edit_text(self, chat_id: str, message_id: str, text: str) -> None:
        await self._call("editMessageText", chat_id=chat_id, message_id=message_id, text=text)

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        await self._call("deleteMessage", chat_id=chat_id, message_id=message_id)

    async def send_typing(
        self, chat_id: str, *, thread_id: str = "", chat_kind: str = "direct"
    ) -> None:
        # Telegram addresses a group by the same chat_id as a DM, so only the
        # thread needs naming — the action then shows in the forum topic the
        # turn is answering in rather than the group's General.
        await self._call(
            "sendChatAction", chat_id=chat_id, action="typing", **thread_target(thread_id)
        )

    async def set_reaction(self, chat_id: str, message_id: str, emoji: str) -> None:
        # FR-036: react on the user's message (👀 receipt / ✅ completion, both in
        # Telegram's fixed allowed set). An empty list would clear; we only set.
        reaction = [{"type": "emoji", "emoji": emoji}]
        await self._call(
            "setMessageReaction", chat_id=chat_id, message_id=message_id, reaction=reaction
        )

    # -- context fetch (ContextFetchPort) -------------------------------------

    async def fetch_thread(
        self, chat_id: str, thread_id: str, *, limit: int = 50, chat_kind: str = "group"
    ) -> tuple[list[ForwardedItem], tuple[InboundAttachment, ...]]:
        # Bot API has no history-fetch method — a bot only ever sees updates
        # pushed to it, never past thread history. Always empty.
        return [], ()

    # -- transport -------------------------------------------------------------

    async def _call(self, method: str, **params: Any) -> Any:
        return await call(self._client, self._base, self._name, method, **params)
