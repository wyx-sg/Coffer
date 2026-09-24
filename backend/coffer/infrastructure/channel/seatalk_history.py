"""Fetching a SeaTalk thread's own messages, and a quoted message, for turn context.

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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from coffer.domain.channel.envelopes import InboundAttachment
from coffer.domain.channel.rich_content import ForwardedItem
from coffer.infrastructure.channel.seatalk_media import thread_media_attachments
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

#: How many pages one turn reads before it stops. Pages run oldest-first, so a
#: thread longer than this loses its NEWEST messages — the cap exists only so a
#: runaway thread cannot stall the turn, and at 20 pages it is far past any
#: thread a person reads through.
_THREAD_PAGE_CAP = 20

_QUOTED_ENDPOINT = "/messaging/v2/get_message_by_message_id"


async def fetch_thread_context(
    get: Callable[[str, dict[str, Any]], Awaitable[Any]],
    client: httpx.AsyncClient,
    media_dir: pathlib.Path,
    ensure_token: Callable[[], Awaitable[str]],
    chat_id: str,
    thread_id: str,
    *,
    limit: int = THREAD_PAGE_MAX,
    channel: str = "",
    chat_kind: str = "group",
) -> tuple[list[ForwardedItem], tuple[InboundAttachment, ...]]:
    """The thread's own messages, when the message landed inside a thread.

    Reads EVERY page: the endpoint pages oldest-first and hands back a
    ``next_cursor`` until the last page, so stopping after the first page would
    drop exactly the messages written just before the @mention. ``limit`` is the
    page size.

    Returns their flattened text AND the images/files they carry, downloaded
    ("Download the media a thread's messages carry") so a picture in the thread reaches the vision
    agent instead of a dead auth-gated file link. Degrades to ``([], ())`` on ANY error so a
    transient failure never breaks the turn, which still runs on the message alone. Group-main
    @mentions fetch no history — that permission is intentionally not granted; the exclusion is
    about the group's MAIN chat, not about groups, so a DM thread is read the same way a group
    thread is.

    ``chat_kind`` picks the endpoint: ``"group"`` reads a group thread by
    ``group_id``, ``"direct"`` reads a DM thread by ``employee_code`` — which in
    a SeaTalk DM is the ``chat_id`` we already hold. Both answer with the same
    ``{"code": 0, "next_cursor": …, "thread_messages": […]}`` body, so the
    flattening and the media download below are shared verbatim. The endpoint
    lookup sits inside the ``try`` deliberately: an unrecognised kind degrades
    and logs like any other failure instead of quietly reading the wrong chat.

    ``code=4010`` means the ``thread_id`` names an unthreaded message — one more
    reason to degrade rather than raise, since the turn is perfectly answerable
    without thread context.
    """
    messages: list[Any] = []
    try:
        endpoint, chat_param = _THREAD_ENDPOINTS[chat_kind]
        params: dict[str, Any] = {chat_param: chat_id, "thread_id": thread_id, "page_size": limit}
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
            return [], ()
    # Recurse: a forwarded record in the thread flattens to its leaves for text,
    # and its images/files download alongside the direct ones.
    return (
        collect_forwarded_items(messages),
        await thread_media_attachments(client, media_dir, ensure_token, messages),
    )


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
    """The adapter's two context reads, bound to its transport once so the adapter
    keeps one-line port methods."""

    get: Callable[[str, dict[str, Any]], Awaitable[Any]]
    client: httpx.AsyncClient
    media_dir: pathlib.Path
    ensure_token: Callable[[], Awaitable[str]]
    channel: str

    async def thread(
        self, chat_id: str, thread_id: str, *, limit: int, chat_kind: str
    ) -> tuple[list[ForwardedItem], tuple[InboundAttachment, ...]]:
        return await fetch_thread_context(
            self.get,
            self.client,
            self.media_dir,
            self.ensure_token,
            chat_id,
            thread_id,
            limit=limit,
            channel=self.channel,
            chat_kind=chat_kind,
        )

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
