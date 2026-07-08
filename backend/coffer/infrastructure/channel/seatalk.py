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
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import httpx

from coffer.application.channel.ports import AdapterCallbacks
from coffer.domain.channel.envelopes import (
    ChannelCapabilities,
    ChoiceButton,
    InboundCallback,
    InboundMessage,
    SentMessage,
)
from coffer.domain.channel.errors import ChannelSendFailed
from coffer.domain.channel.rich_content import ForwardedItem
from coffer.infrastructure.channel.seatalk_parse import (
    collect_forwarded_items,
    flatten_combined_forwarded,
    interactive_card,
    split_to_byte_limit,
    strip_group_mentions,
)

_logger = logging.getLogger(__name__)

_CHUNK_LIMIT = 3500  # paragraph-chunking budget, in characters
_BYTE_LIMIT = 3900  # SeaTalk caps content at 4096 BYTES; stay clear of it

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
            supports_typing=True,
            max_message_chars=_CHUNK_LIMIT,
            supports_buttons=True,
            supports_groups=True,
            supports_history_fetch=True,
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
                    chat_kind="group",
                    addressed=True,
                    thread_id=reply_thread_id,
                )
            )
        elif event_type in (
            "new_message_received_from_thread",
            "bot_added_to_group_chat",
            "user_enter_chatroom_with_bot",
        ):
            # A thread @mention already arrives as
            # new_mentioned_message_received_from_group_chat with thread_id
            # set; non-@ thread chatter and group-membership events must never
            # start a turn.
            return
        elif event_type == "interactive_message_click" and self._callbacks.on_callback is not None:
            # A selection-card button tap; the custom ``value`` we set on the
            # button comes back here (research.md). DMs are 1:1 so the sender is
            # the employee_code — the core owner-gates on it.
            await self._callbacks.on_callback(
                InboundCallback(
                    channel=self._name,
                    chat_id=str(event.get("employee_code", "")),
                    sender_id=str(event.get("employee_code", "")),
                    data=str(event.get("value", "")),
                    platform_message_id=str(event.get("message_id", "")),
                )
            )

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
        from coffer.infrastructure.channel.render import chunk_text

        if buttons:
            # Selection prompts are short — one interactive card, no chunking.
            result = await self._send(
                chat_id, interactive_card(markdown, buttons), thread_id, chat_kind
            )
            return SentMessage(message_id=str(result.get("message_id", "")))
        last = ""
        for chunk in chunk_text(markdown, self.capabilities.max_message_chars):
            for piece in split_to_byte_limit(chunk, _BYTE_LIMIT):
                result = await self._send(
                    chat_id,
                    {"tag": "text", "text": {"format": 1, "content": piece}},
                    thread_id,
                    chat_kind,
                )
                last = str(result.get("message_id", ""))
        return SentMessage(message_id=last)

    async def _send(
        self, chat_id: str, message: dict[str, Any], thread_id: str, chat_kind: str
    ) -> Any:
        """Route one already-built ``message`` payload to the group or
        single-chat endpoint, sharing the chunk loop above across both."""
        if chat_kind == "group":
            return await self._send_group_chat(chat_id, message, thread_id)
        return await self._send_single_chat(chat_id, message, thread_id)

    async def edit_text(self, chat_id: str, message_id: str, text: str) -> None:
        raise ChannelSendFailed(self._name, "seatalk cannot edit messages")

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        raise ChannelSendFailed(self._name, "seatalk cannot delete messages")

    async def send_typing(self, chat_id: str) -> None:
        with contextlib.suppress(Exception):
            await self._post(
                "/messaging/v2/single_chat_typing", {"employee_code": chat_id}, retries=0
            )

    async def send_media(
        self,
        chat_id: str,
        path: str,
        *,
        caption: str | None = None,
        as_photo: bool = True,
    ) -> SentMessage:
        # SeaTalk file upload is not wired yet; capabilities.supports_media is
        # False so the core never calls this. Present to satisfy the Protocol.
        raise ChannelSendFailed(self._name, "seatalk cannot send media yet")

    # -- context fetch (ContextFetchPort) -------------------------------------

    async def fetch_thread(
        self, chat_id: str, thread_id: str, *, limit: int = 50
    ) -> list[ForwardedItem]:
        """The thread's own messages, when the @mention landed inside a
        thread rather than the group main chat. Degrades to ``[]`` on ANY
        error (a network hiccup, an unexpected payload, or a permission gap):
        a transient failure must not break the turn, which still runs on the
        @mention message alone. (Group-main @mentions fetch no history — that
        permission is intentionally not granted.)"""
        try:
            payload = await self._get(
                "/messaging/v2/group_chat/get_thread_by_thread_id",
                {"group_id": chat_id, "thread_id": thread_id, "page_size": limit},
            )
        except Exception:
            _logger.warning(
                "seatalk.fetch_thread.failed", extra={"channel": self._name}, exc_info=True
            )
            return []
        messages = payload.get("thread_messages") or [] if isinstance(payload, dict) else []
        # Recurse: a forwarded record in the thread flattens to its leaves.
        return collect_forwarded_items(messages)

    # -- transport -------------------------------------------------------------

    async def _send_single_chat(
        self, employee_code: str, message: dict[str, Any], thread_id: str = ""
    ) -> Any:
        # FR-026: thread the reply by carrying thread_id on the message body.
        if thread_id:
            message = {**message, "thread_id": thread_id}
        return await self._post(
            "/messaging/v2/single_chat",
            {"employee_code": employee_code, "message": message},
        )

    async def _send_group_chat(self, group_id: str, message: dict[str, Any], thread_id: str) -> Any:
        return await self._post(
            "/messaging/v2/group_chat",
            {
                "group_id": group_id,
                "message": message,
                **({"thread_id": thread_id} if thread_id else {}),
            },
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

    async def _get(self, path: str, params: dict[str, Any], *, retries: int = 3) -> Any:
        """GET counterpart of :meth:`_post` — same token/refresh/rate-limit/
        non-JSON handling, but for the read-only history/thread endpoints
        which take query params, not a JSON body."""
        attempt = 0
        while True:
            token = await self._ensure_token()
            try:
                response = await self._client.get(
                    f"{self._base}{path}",
                    params=params,
                    headers={"Authorization": f"Bearer {token}"},
                )
            except httpx.HTTPError as e:
                raise ChannelSendFailed(self._name, f"{path}: {type(e).__name__}") from e
            try:
                payload: Any = response.json()
            except ValueError as e:
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
