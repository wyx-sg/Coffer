"""SeaTalk transport: callback events in (via the listener), Open APIs out.

No SDK: ``seatalk_transport`` owns the token cache and the Open API request
shapes; this module normalizes inbound events, which arrive through the
daemon's events-ingest route (the callback listener forwards them) — it owns
no poll loop.
"""

from __future__ import annotations

import pathlib
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import httpx

from coffer.application.channel.ports import AdapterCallbacks
from coffer.domain.channel.dedup import SeenIds
from coffer.domain.channel.envelopes import (
    ChannelCapabilities,
    ChoiceButton,
    EphemeralTarget,
    InboundAttachment,
    InboundCallback,
    InboundLifecycle,
    InboundMessage,
    SentMessage,
)
from coffer.domain.channel.errors import ChannelSendFailed
from coffer.domain.channel.rich_content import ForwardedItem
from coffer.infrastructure.channel.live_text import SeaTalkLiveText
from coffer.infrastructure.channel.seatalk_cards import update_interactive_card
from coffer.infrastructure.channel.seatalk_history import fetch_thread_context
from coffer.infrastructure.channel.seatalk_media import (
    default_media_dir,
    media_attachments,
    send_outbound_media,
)
from coffer.infrastructure.channel.seatalk_parse import (
    dedup_key,
    flatten_combined_forwarded,
    mentions_others,
    strip_group_mentions,
)
from coffer.infrastructure.channel.seatalk_send import (
    SEATALK_MENTION_EMAIL_TEMPLATE,
    SEATALK_MENTION_TEMPLATE,
    send_text_pieces,
)
from coffer.infrastructure.channel.seatalk_transport import SeaTalkTransport
from coffer.infrastructure.channel.seatalk_typing import send_typing

_CHUNK_LIMIT = 3500  # paragraph-chunking budget, in characters
_BYTE_LIMIT = 3900  # SeaTalk caps content at 4096 BYTES; stay clear of it


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
        media_dir: pathlib.Path | None = None,
    ) -> None:
        self._name = channel_name
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=30.0))
        self._media_dir = media_dir or default_media_dir()
        self._callbacks: AdapterCallbacks | None = None
        self._seen = SeenIds()  # FR-039: drop redelivered events
        self._transport = SeaTalkTransport(channel_name, app_id, app_secret, base_url, self._client)
        # One chat_kind-routed send seam for every outbound payload — text
        # chunks, cards, media (``send_outbound_media`` takes it as a callable).
        self._send = self._transport.send

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            supports_edit=False,  # no API rewrites a delivered SeaTalk message
            # FR-037: but a message CAN grow in place — init_stream/update_stream.
            supports_live_text=True,
            live_text_persists=True,  # the streamed message IS the reply
            # Both chat kinds: single_chat_typing and group_chat_typing. The
            # group one silently no-ops above 200 members (code 7003), so this
            # promises an attempt, never a delivered receipt.
            supports_typing=True,
            max_message_chars=_CHUNK_LIMIT,
            supports_buttons=True,
            # Update Message covers interactive cards (never text — see supports_edit).
            supports_card_update=True,
            supports_media=True,
            supports_groups=True,
            supports_history_fetch=True,
            # FR-070: SeaTalk mentions from a bare id, so a group reply can open
            # by @mentioning whoever asked without resolving a display name. Its
            # documented email form is the fallback for a sender with no id.
            mention_template=SEATALK_MENTION_TEMPLATE,
            mention_email_template=SEATALK_MENTION_EMAIL_TEMPLATE,
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
        # FR-039: SeaTalk retries a slow callback and a network hiccup can
        # double-deliver — drop an event whose id (or message id) we already
        # processed so a redelivery never drives the same turn twice. The
        # verification handshake never reaches here (the listener answers it).
        key = dedup_key(envelope, event)
        if key and not self._seen.add(key):
            return
        if event_type == "message_from_bot_subscriber":
            message = event.get("message") or {}
            tag = str(message.get("tag", ""))
            text = ""
            if tag == "text":
                text = str((message.get("text") or {}).get("content", ""))
            elif tag == "combined_forwarded_chat_history":
                text = flatten_combined_forwarded(message)
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
                    # SeaTalk DMs are 1:1, so the sender is the employee_code.
                    sender_id=str(event.get("employee_code", "")),
                    thread_id=str(message.get("thread_id", "")),
                    # Hand the turn the id and stop: the quoted BODY comes from
                    # GET /messaging/v2/get_message_by_message_id, an agent-invoked
                    # lookup (SeaTalk's MCP server exposes it under that name), not
                    # transport work. The docs warn one message carries DIFFERENT
                    # message_ids per app — only this bot can resolve this one.
                    quoted_message_id=str(message.get("quoted_message_id") or ""),
                    attachments=await media_attachments(
                        self._client, self._media_dir, self._transport.ensure_token, message
                    ),
                )
            )
        elif event_type == "new_mentioned_message_received_from_group_chat":
            # SeaTalk only fires this event when the bot is @mentioned (it
            # pre-filters group traffic) — always addressed by definition.
            message = event.get("message") or {}
            sender = message.get("sender") or {}
            tag = str(message.get("tag", ""))
            if tag == "combined_forwarded_chat_history":
                # Same flattening as the DM path (a bare plain_text lookup would drop it).
                plain_text = flatten_combined_forwarded(message)
            else:
                body = message.get("text") or {}
                plain_text = strip_group_mentions(
                    str(body.get("plain_text", "")), body.get("mentioned_list")
                )
            message_id = str(message.get("message_id", ""))
            # A group reply must land in a thread, never the main chat. A thread's
            # id == its root message_id, so an in-thread @mention already carries it
            # and a main-chat one ("") roots a fresh thread here — fall back to this id.
            reply_thread_id = str(message.get("thread_id", "")) or message_id
            await self._callbacks.on_message(
                InboundMessage(
                    channel=self._name,
                    chat_id=str(event.get("group_id", "")),
                    sender_display=str(sender.get("email", "") or sender.get("seatalk_id", "")),
                    text=plain_text,
                    platform_message_id=message_id,
                    timestamp=datetime.fromtimestamp(
                        int(envelope.get("timestamp", 0) or 0), tz=UTC
                    ),
                    sender_id=str(sender.get("employee_code", "")),
                    # FR-070: the id an outbound @mention points at, kept apart
                    # from sender_id because they are different values here —
                    # and because the docs warn employee_code and email arrive
                    # EMPTY for a sender outside the bot's organisation, which
                    # leaves seatalk_id as the only id such a message carries.
                    sender_mention_id=str(sender.get("seatalk_id", "")),
                    # …and the address only as its fallback (see above).
                    sender_mention_email=str(sender.get("email", "")),
                    chat_kind="group",
                    addressed=True,
                    # FR-035: >1 distinct @mentioned username ⇒ a non-bot user
                    # was mentioned alongside the bot (empty for a forwarded record).
                    mentions_others=mentions_others(
                        (message.get("text") or {}).get("mentioned_list")
                    ),
                    thread_id=reply_thread_id,
                    quoted_message_id=str(message.get("quoted_message_id") or ""),
                    attachments=await media_attachments(
                        self._client, self._media_dir, self._transport.ensure_token, message
                    ),
                )
            )
        elif event_type == "bot_removed_from_group_chat":
            # Not a turn — a change in what the binding IS: every later send
            # to this group would fail. The remover is named the way
            # sender_display is everywhere here (email, else seatalk_id).
            remover = event.get("remover") or {}
            actor = str(remover.get("email", "") or remover.get("seatalk_id", ""))
            await self._lifecycle(str(event.get("group_id", "")), "removed_from_group", actor)
        elif event_type == "group_chat_converted_to_external_group":
            # Readers outside the organisation can now see what lands here.
            # SeaTalk names nobody in this event, so actor_display stays "".
            await self._lifecycle(str(event.get("group_id", "")), "group_became_external")
        elif event_type in (
            "new_message_received_from_thread",
            "bot_added_to_group_chat",
            "user_enter_chatroom_with_bot",
        ):
            # What stays dropped, for one reason: nothing above the adapter acts
            # on it. A thread @mention already arrives as
            # new_mentioned_message_received_from_group_chat with thread_id set,
            # so non-@ thread chatter is noise; being ADDED to a group (unlike
            # being removed) changes nothing — the user creates the binding.
            return
        elif event_type == "interactive_message_click" and self._callbacks.on_callback is not None:
            # A selection-card button tap; the custom ``value`` we set on the
            # button comes back here (research.md). A group card tap carries a
            # ``group_id`` and a DM tap does not — derive chat_kind from that so
            # the core replies into the group/thread and owner-gates on the right
            # peer (FR-034). DMs are 1:1 so the sender IS the employee_code; a
            # group tap names the tapper under ``sender``, like the @mention.
            group_id = str(event.get("group_id", ""))
            sender = event.get("sender") or {}
            sender_id = str(sender.get("employee_code", "") or event.get("employee_code", ""))
            await self._callbacks.on_callback(
                InboundCallback(
                    channel=self._name,
                    chat_id=group_id or str(event.get("employee_code", "")),
                    sender_id=sender_id,
                    data=str(event.get("value", "")),
                    platform_message_id=str(event.get("message_id", "")),
                    chat_kind="group" if group_id else "direct",
                    thread_id=str(event.get("thread_id", "")),
                )
            )

    async def _lifecycle(self, chat_id: str, kind: str, actor: str = "") -> None:
        """Report a standing change — only when the core asked to hear them."""
        callbacks = self._callbacks
        if callbacks is None or callbacks.on_lifecycle is None:
            return
        await callbacks.on_lifecycle(
            InboundLifecycle(channel=self._name, chat_id=chat_id, kind=kind, actor_display=actor)
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
        # SeaTalk has no reply primitive — a message cannot point at another —
        # so the reply target is accepted and ignored (FR-068); nor can it show
        # a group message to one member only (FR-064).
        del reply_to_message_id, ephemeral
        return await send_text_pieces(
            self._send,
            chat_id,
            markdown,
            char_limit=self.capabilities.max_message_chars,
            byte_limit=_BYTE_LIMIT,
            buttons=buttons,
            title=title,
            thread_id=thread_id,
            chat_kind=chat_kind,
        )

    async def open_live_text(
        self, chat_id: str, *, thread_id: str = "", chat_kind: str = "direct"
    ) -> SeaTalkLiveText:
        """FR-037: SeaTalk cannot edit, but it can stream — one message that
        re-renders from the full snapshot until the stream is finished."""
        return SeaTalkLiveText(
            self._post, chat_id, name=self._name, thread_id=thread_id, chat_kind=chat_kind
        )

    async def edit_text(self, chat_id: str, message_id: str, text: str) -> None:
        # supports_edit stays literally false: no SeaTalk API rewrites a
        # delivered TEXT message. Live progress goes through open_live_text, and
        # a delivered CARD is rewritable through update_card below.
        raise ChannelSendFailed(self._name, "seatalk cannot edit messages")

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
        del chat_kind  # the message id identifies the message; no chat routing
        await update_interactive_card(self._post, message_id, markdown, buttons, title=title)

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        raise ChannelSendFailed(self._name, "seatalk cannot delete messages")

    async def set_reaction(self, chat_id: str, message_id: str, emoji: str) -> None:
        # FR-036: SeaTalk has no outbound reaction API — capabilities report
        # supports_reactions=False, so the core never calls this (it uses the
        # typing signal for the same receipt cue); the Protocol still needs it.
        raise ChannelSendFailed(self._name, "seatalk cannot set reactions")

    async def send_typing(
        self,
        chat_id: str,
        *,
        thread_id: str = "",
        chat_kind: str = "direct",
        action: str = "typing",
    ) -> None:
        # SeaTalk has one busy signal; what the bot is busy doing is not
        # expressible, so the action is accepted and ignored.
        del action
        await send_typing(self._post, chat_id, thread_id, chat_kind)

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
        """Upload a local file through the endpoints send_text uses (via
        ``send_outbound_media``): an image (by extension) as a SeaTalk ``image``
        message, else a ``file`` message (base64 content), routed through
        ``_send`` into the same chat_kind + thread the turn came from (FR-031).
        ``as_photo`` is unused — SeaTalk picks preview-vs-attachment by tag."""
        del as_photo
        message_id = await send_outbound_media(
            self._send, chat_id, path, caption=caption, thread_id=thread_id, chat_kind=chat_kind
        )
        return SentMessage(message_id=message_id)

    # -- context fetch (ContextFetchPort) -------------------------------------

    async def fetch_thread(
        self, chat_id: str, thread_id: str, *, limit: int = 50, chat_kind: str = "group"
    ) -> tuple[list[ForwardedItem], tuple[InboundAttachment, ...]]:
        """The thread's own messages, when the message landed inside a thread.

        Threads are no longer group-only (SeaTalk app v3.62.1+ has them in DMs),
        so ``chat_kind`` picks the read endpoint — the group @mention is just the
        common case. Delegates to ``seatalk_history`` so this file stays inside
        the size cap; see there for the degrade-to-empty contract.
        """
        return await fetch_thread_context(
            self._get,
            self._client,
            self._media_dir,
            self._transport.ensure_token,
            chat_id,
            thread_id,
            limit=limit,
            channel=self._name,
            chat_kind=chat_kind,
        )

    # -- transport -------------------------------------------------------------

    async def _post(self, path: str, body: dict[str, Any], *, retries: int = 3) -> Any:
        return await self._transport.request("POST", path, json=body, retries=retries)

    async def _get(self, path: str, params: dict[str, Any], *, retries: int = 3) -> Any:
        return await self._transport.request("GET", path, params=params, retries=retries)
