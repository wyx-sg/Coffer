"""Reading a SeaTalk thread's own messages, and a quoted message, for turn context.

A helper module beside ``seatalk.py``, like ``seatalk_media.py`` and
``seatalk_parse.py``: the adapter keeps the port method, the work lives here so
that file stays inside the size cap.

Threads are not a group-only feature: SeaTalk threads a DM too, and publishes a
separate single-chat endpoint for reading one (app v3.62.1+). The two endpoints
differ only in their name and in how the chat is identified — ``group_id`` there,
``employee_code`` here — and return the same body, so one code path serves both.
"""

from __future__ import annotations

import logging
import pathlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from coffer.domain.channel.envelopes import InboundAttachment
from coffer.domain.channel.rich_content import ForwardedItem
from coffer.domain.channel.thread_messages import ThreadMessage, ThreadRead
from coffer.infrastructure.channel.seatalk_media import collect_media, thread_media_attachments
from coffer.infrastructure.channel.seatalk_parse import collect_forwarded_items

_logger = logging.getLogger(__name__)

#: The thread-read endpoint per chat kind, and the parameter naming the chat on
#: it. A DM's ``chat_id`` IS the peer's ``employee_code``, which is the only
#: reason the same ``chat_id`` argument can feed both.
_THREAD_ENDPOINTS = {
    "group": ("/messaging/v2/group_chat/get_thread_by_thread_id", "group_id"),
    "direct": ("/messaging/v2/single_chat/get_thread_by_thread_id", "employee_code"),
}

#: The largest ``page_size`` the thread endpoints accept (101 answers code 102).
THREAD_PAGE_MAX = 100

#: How many pages one read takes before it stops. Pages run oldest-first, so a
#: thread longer than this loses its NEWEST messages — the cap exists only so a
#: runaway thread cannot stall the turn, and at 20 pages it is far past any
#: thread a person reads through.
_THREAD_PAGE_CAP = 20

#: How far back the thread endpoints reach: replies older than this are never
#: returned, whatever the app shows. A root message is exempt, so an old thread
#: comes back as its root plus the recent replies and looks nearly empty.
THREAD_WINDOW_SECONDS = 7 * 24 * 60 * 60

#: What a thread whose root predates the window cannot show (spec channels "Say
#: what a thread read cannot show").
WINDOW_NOTE = (
    "SeaTalk returns only the last 7 days of a thread's replies; this thread began "
    "earlier, so older messages in it are not shown here and cannot be read."
)

#: ``sender.sender_type`` of a message a bot sent (1 is a person, 3 a system account).
_SENDER_TYPE_BOT = 2


def _older_than_window(messages: list[dict[str, Any]], now: float) -> bool:
    """Whether any returned message predates the thread endpoints' reach — only the
    root can, so this says the thread's earlier replies were cut off."""
    return any(
        isinstance(m.get("message_sent_time"), int | float)
        and now - m["message_sent_time"] > THREAD_WINDOW_SECONDS
        for m in messages
    )


_QUOTED_ENDPOINT = "/messaging/v2/get_message_by_message_id"


def to_thread_message(message: dict[str, Any]) -> ThreadMessage:
    """One raw thread message as the core's :class:`ThreadMessage`; the raw dict
    rides along as its ``handle`` for the media download."""
    sender = message.get("sender") or {}
    from_bot = sender.get("sender_type") == _SENDER_TYPE_BOT
    sent = message.get("message_sent_time")
    return ThreadMessage(
        message_id=str(message.get("message_id") or ""),
        sender=str(sender.get("email") or ("bot" if from_bot else "unknown")),
        sent_at=datetime.fromtimestamp(sent, tz=UTC) if isinstance(sent, int | float) else None,
        # Recurse: a forwarded record flattens to its leaves with their own senders.
        items=tuple(collect_forwarded_items([message])),
        from_bot=from_bot,
        has_media=bool(collect_media(message)),
        handle=message,
    )


async def fetch_thread_context(
    get: Callable[[str, dict[str, Any]], Awaitable[Any]],
    chat_id: str,
    thread_id: str,
    *,
    channel: str = "",
    chat_kind: str = "group",
) -> ThreadRead:
    """The thread's own messages, oldest first, with no media downloaded.

    Reads EVERY page: the endpoint pages oldest-first and hands back a
    ``next_cursor`` until the last page, so the newest messages — the ones a
    turn grounds on — are only reached by reading to the end. Text only, which
    is cheap; the core downloads the media of just the messages it keeps
    (:func:`message_media`).

    ``chat_kind`` picks the endpoint: ``"group"`` reads a group thread by
    ``group_id``, ``"direct"`` reads a DM thread by ``employee_code`` — which in
    a SeaTalk DM is the ``chat_id`` we already hold. Both answer with the same
    ``{"code": 0, "next_cursor": …, "thread_messages": […]}`` body. The endpoint
    lookup sits inside the ``try`` deliberately: an unrecognised kind fails the
    read like any other failure instead of quietly reading the wrong chat.

    Group-main @mentions read no history — that permission is intentionally not
    granted; the exclusion is about the group's MAIN chat, not about groups, so
    a DM thread is read the same way a group thread is. ``code=4010`` (the
    ``thread_id`` names an unthreaded message) is one more failed read.
    """
    messages: list[Any] = []
    try:
        endpoint, chat_param = _THREAD_ENDPOINTS[chat_kind]
        params: dict[str, Any] = {
            chat_param: chat_id,
            "thread_id": thread_id,
            "page_size": THREAD_PAGE_MAX,
        }
        for _ in range(_THREAD_PAGE_CAP):
            payload = await get(endpoint, params)
            if not isinstance(payload, dict):
                break
            messages.extend(payload.get("thread_messages") or [])
            cursor = str(payload.get("next_cursor") or "")
            if not cursor:
                break
            params = {**params, "cursor": cursor}
    except Exception:
        # A failed later page keeps the pages already read: an older slice of the
        # thread still grounds the turn better than none.
        _logger.warning("seatalk.fetch_thread.failed", extra={"channel": channel}, exc_info=True)
        if not messages:
            return ThreadRead(failed=True)
    dicts = [m for m in messages if isinstance(m, dict)]
    return ThreadRead(
        messages=tuple(to_thread_message(m) for m in dicts),
        window_note=WINDOW_NOTE if _older_than_window(dicts, time.time()) else "",
    )


async def message_media(
    client: httpx.AsyncClient,
    media_dir: pathlib.Path,
    ensure_token: Callable[[], Awaitable[str]],
    message: ThreadMessage,
) -> tuple[InboundAttachment, ...]:
    """Download what one thread message carries ("Download the media a thread's
    messages carry"), recursing into a forwarded record, so a picture reaches the
    vision agent instead of a dead auth-gated file link. Each failed download is
    skipped; a message this module did not read carries nothing to download."""
    if not message.has_media or not isinstance(message.handle, dict):
        return ()
    return await thread_media_attachments(client, media_dir, ensure_token, [message.handle])


async def fetch_quoted_context(
    get: Callable[[str, dict[str, Any]], Awaitable[Any]],
    client: httpx.AsyncClient,
    media_dir: pathlib.Path,
    ensure_token: Callable[[], Awaitable[str]],
    message_id: str,
    *,
    channel: str = "",
) -> tuple[list[ForwardedItem], tuple[InboundAttachment, ...]]:
    """The message a turn quotes, resolved with THIS bot's own token.

    SeaTalk gives one message a different ``message_id`` per app, so the quoted
    id an event carries resolves only for the app that received it — no other
    tool the agent holds could look it up. The response body has the same shape
    as a thread message, so it flattens and downloads through the same helpers.
    Degrades to ``([], ())`` on any error or a non-zero ``code``: the turn still
    runs, and its origin block still names the quoted id.
    """
    try:
        payload = await get(_QUOTED_ENDPOINT, {"message_id": message_id})
    except Exception:
        _logger.warning("seatalk.fetch_quoted.failed", extra={"channel": channel}, exc_info=True)
        return [], ()
    if not isinstance(payload, dict) or payload.get("code", 0) != 0:
        return [], ()
    return (
        collect_forwarded_items([payload]),
        await thread_media_attachments(client, media_dir, ensure_token, [payload]),
    )


@dataclass(frozen=True)
class SeaTalkContextReader:
    """The adapter's context reads, bound to its transport once so the adapter
    keeps one-line port methods."""

    get: Callable[[str, dict[str, Any]], Awaitable[Any]]
    client: httpx.AsyncClient
    media_dir: pathlib.Path
    ensure_token: Callable[[], Awaitable[str]]
    channel: str

    async def thread(self, chat_id: str, thread_id: str, *, chat_kind: str) -> ThreadRead:
        return await fetch_thread_context(
            self.get, chat_id, thread_id, channel=self.channel, chat_kind=chat_kind
        )

    async def media(self, message: ThreadMessage) -> tuple[InboundAttachment, ...]:
        return await message_media(self.client, self.media_dir, self.ensure_token, message)

    async def quoted(
        self, message_id: str
    ) -> tuple[list[ForwardedItem], tuple[InboundAttachment, ...]]:
        return await fetch_quoted_context(
            self.get,
            self.client,
            self.media_dir,
            self.ensure_token,
            message_id,
            channel=self.channel,
        )
