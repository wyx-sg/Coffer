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
    EphemeralTarget,
    InboundAttachment,
    InboundMessage,
    SentMessage,
)
from coffer.domain.channel.rich_content import ForwardedItem
from coffer.infrastructure.channel.live_text import TelegramLiveText
from coffer.infrastructure.channel.telegram_album import AlbumBuffer
from coffer.infrastructure.channel.telegram_cards import edit_card
from coffer.infrastructure.channel.telegram_draft import TelegramDraftLiveText
from coffer.infrastructure.channel.telegram_features import FeatureSet
from coffer.infrastructure.channel.telegram_media import (
    FetchedMedia,
    default_media_dir,
    download_attachments,
    upload_media,
)
from coffer.infrastructure.channel.telegram_parse import (
    build_inbound_message,
    thread_target,
)
from coffer.infrastructure.channel.telegram_poll import poll_updates
from coffer.infrastructure.channel.telegram_profile import (
    BotIdentity,
    probe_identity,
    register_profile,
)
from coffer.infrastructure.channel.telegram_rich import RICH_MESSAGE_LIMIT
from coffer.infrastructure.channel.telegram_send import send_text_chunks
from coffer.infrastructure.channel.telegram_transport import call
from coffer.infrastructure.channel.telegram_updates import (
    callback_from_query,
    lifecycle_from_update,
    stop_from_update,
    tap_ack,
)

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
        self._profile_task: asyncio.Task[None] | None = None
        # FR-059: what getMe said about this bot, filled in start(). Defaults
        # are the "could not introspect" state, never a guess.
        self._identity = BotIdentity()
        # FR-059: Bot API 10.x capabilities, each live until the platform
        # itself refuses it. Per-adapter: two channels may point at different
        # Bot API servers.
        self._features = FeatureSet()

    @property
    def identity(self) -> BotIdentity:
        """What ``getMe`` reported (FR-059). Read by the channel health surface
        to diagnose a privacy-mode/configuration contradiction (FR-060)."""
        return self._identity

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            supports_edit=True,
            supports_live_text=True,  # FR-037: the edit IS its live surface
            supports_typing=True,
            # FR-061: a rich message carries 32k characters against an ordinary
            # message's 4k, so the chunk budget follows whether the platform
            # still accepts them — and drops back the moment it does not.
            max_message_chars=(
                RICH_MESSAGE_LIMIT if self._features.rich_messages.available else _CHUNK_LIMIT
            ),
            supports_buttons=True,
            supports_card_update=True,  # editMessageText rewrites text + keyboard
            supports_media=True,
            supports_groups=True,
            supports_reactions=True,
        )

    # -- lifecycle ---------------------------------------------------------

    async def start(self, callbacks: AdapterCallbacks) -> None:
        self._callbacks = callbacks
        # FR-059: probe, never assume — identity for @mention matching, and the
        # privacy-mode flag the health surface reports on (FR-060). Awaited,
        # because parsing a group message needs the bot's own id.
        self._identity = await probe_identity(self._call)
        # FR-065: register the command menu and fill an empty profile. NOT
        # awaited: it is up to six best-effort calls that nothing depends on,
        # and the reconciler is waiting on start() — against an unreachable API
        # they would hold up the channel for a minute to change nothing.
        self._profile_task = asyncio.create_task(
            register_profile(self._call), name=f"telegram-profile:{self._name}"
        )
        self._task = asyncio.create_task(self._poll_loop(), name=f"telegram-poll:{self._name}")

    async def stop(self) -> None:
        # FR-038: drop pending album timers/flush tasks so none leak past stop.
        self._albums.cancel_all()
        if self._profile_task is not None:
            self._profile_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._profile_task
            self._profile_task = None
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self._client.aclose()

    # -- inbound -------------------------------------------------------------

    async def _poll_loop(self) -> None:
        await poll_updates(
            self._call, self._dispatch, channel=self._name, timeout=self._poll_timeout
        )

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
            fetched = await self._download_attachments(message)
            media_group_id = message.get("media_group_id")
            if media_group_id:
                # FR-038: an album arrives as separate updates sharing a media_group_id
                # — buffer them and flush ONE turn (FR-039 dedup still runs per-update).
                self._albums.add(str(media_group_id), message, fetched.attachments, fetched.notes)
                return
            await self._callbacks.on_message(
                self._build_inbound(message, fetched.attachments, fetched.notes)
            )
            return
        query = update.get("callback_query")
        if isinstance(query, dict):
            await self._dispatch_callback(query)
            return
        # FR-063: the user pressed the stop control on a streamed draft.
        stopped = stop_from_update(update, channel=self._name)
        if stopped is not None:
            if self._callbacks.on_stop is not None:
                await self._callbacks.on_stop(stopped)
            return
        # The bot was removed from a chat (FR-058) — the same event SeaTalk
        # reports directly, arriving here as a membership transition.
        lifecycle = lifecycle_from_update(update, channel=self._name, bot_id=self._identity.bot_id)
        if lifecycle is not None and self._callbacks.on_lifecycle is not None:
            await self._callbacks.on_lifecycle(lifecycle)

    def _build_inbound(
        self,
        message: dict[str, Any],
        attachments: tuple[InboundAttachment, ...],
        notes: tuple[str, ...] = (),
    ) -> InboundMessage:
        return build_inbound_message(
            message,
            attachments,
            channel=self._name,
            bot_id=self._identity.bot_id,
            bot_username=self._identity.username,
            notes=notes,
        )

    async def _flush_album(
        self,
        message: dict[str, Any],
        attachments: tuple[InboundAttachment, ...],
        notes: tuple[str, ...],
    ) -> None:
        """FR-038: emit ONE InboundMessage for a debounced album — all its
        attachments and the caption from whichever item carried it."""
        if self._callbacks is None:
            return
        await self._callbacks.on_message(self._build_inbound(message, attachments, notes))

    async def _download_attachments(self, message: dict[str, Any]) -> FetchedMedia:
        return await download_attachments(
            self._client, self._call, self._file_base, self._media_dir, self._name, message
        )

    async def _dispatch_callback(self, query: dict[str, Any]) -> None:
        if self._callbacks is None:
            return
        query_id = str(query.get("id") or "")
        if self._callbacks.on_callback is not None:
            await self._callbacks.on_callback(callback_from_query(query, channel=self._name))
        # Dismiss the button's loading spinner AND say what was taken, so the
        # tap has immediate feedback even before the card rewrite lands
        # (best-effort; the tap itself is already handled).
        if query_id:
            with contextlib.suppress(Exception):
                await self._call(
                    "answerCallbackQuery",
                    callback_query_id=query_id,
                    text=tap_ack(str(query.get("data") or "")),
                )

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
        reply_to_message_id: str = "",
        ephemeral: EphemeralTarget | None = None,
    ) -> SentMessage:
        # chat_kind is unused: a Telegram chat_id addresses a DM and a group alike.
        del chat_kind
        return await send_text_chunks(
            self._call,
            chat_id,
            markdown,
            limit=_CHUNK_LIMIT,
            buttons=buttons,
            title=title,
            thread_id=thread_id,
            reply_to_message_id=reply_to_message_id,
            channel=self._name,
            rich=self._features.rich_messages,
            ephemeral=ephemeral,
            ephemeral_feature=self._features.ephemeral_messages,
        )

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

    async def open_live_text(
        self, chat_id: str, *, thread_id: str = "", chat_kind: str = "direct"
    ) -> TelegramLiveText | TelegramDraftLiveText:
        """FR-037/FR-062: a surface the reply grows on.

        A message draft is the platform's own answer to this and is preferred
        where it exists: nothing is delivered, so nothing has to be deleted
        afterwards, and it carries the stop control FR-063 routes back here.

        Two things send a turn back to the older mechanism — one sent message,
        rewritten in place. A Bot API server that has never heard of drafts is
        the obvious one. The other is a group: ``sendMessageDraft`` addresses
        "the target private chat" and has no group form, so a group turn would
        spend a refused round trip per snapshot and show no progress at all.
        Keeping the stop control out of groups is a second reason to prefer the
        DM-only split: the stop update names no sender, so a button any member
        could press is a button Coffer could not owner-gate.
        """
        if chat_kind != "group" and self._features.message_drafts.available:
            return TelegramDraftLiveText(
                self._call,
                chat_id,
                channel=self._name,
                feature=self._features.message_drafts,
                thread_id=thread_id,
            )
        return TelegramLiveText(self._call, chat_id, thread_id=thread_id)

    async def edit_text(self, chat_id: str, message_id: str, text: str) -> None:
        await self._call("editMessageText", chat_id=chat_id, message_id=message_id, text=text)

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        await self._call("deleteMessage", chat_id=chat_id, message_id=message_id)

    async def send_typing(
        self,
        chat_id: str,
        *,
        thread_id: str = "",
        chat_kind: str = "direct",
        action: str = "typing",
    ) -> None:
        """Show what the bot is busy doing. ``action`` lets an upload say so
        ("upload_photo" / "upload_document") instead of claiming to type.

        Telegram addresses a group by the same chat_id as a DM, so only the
        thread needs naming — the action then shows in the forum topic the turn
        is answering in rather than the group's General.
        """
        del chat_kind
        await self._call(
            "sendChatAction", chat_id=chat_id, action=action, **thread_target(thread_id)
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
