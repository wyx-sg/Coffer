"""Fetching a SeaTalk thread's own messages for turn context.

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


async def fetch_thread_context(
    get: Callable[[str, dict[str, Any]], Awaitable[Any]],
    client: httpx.AsyncClient,
    media_dir: pathlib.Path,
    ensure_token: Callable[[], Awaitable[str]],
    chat_id: str,
    thread_id: str,
    *,
    limit: int = 50,
    channel: str = "",
    chat_kind: str = "group",
) -> tuple[list[ForwardedItem], tuple[InboundAttachment, ...]]:
    """The thread's own messages, when the message landed inside a thread.

    Returns their flattened text AND the images/files they carry, downloaded
    (FR-029) so a picture in the thread reaches the vision agent instead of a
    dead auth-gated file link. Degrades to ``([], ())`` on ANY error so a
    transient failure never breaks the turn, which still runs on the message
    alone. Group-main @mentions fetch no history — that permission is
    intentionally not granted; the exclusion is about the group's MAIN chat, not
    about groups, so a DM thread is read the same way a group thread is.

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
    try:
        endpoint, chat_param = _THREAD_ENDPOINTS[chat_kind]
        payload = await get(
            endpoint,
            {chat_param: chat_id, "thread_id": thread_id, "page_size": limit},
        )
    except Exception:
        _logger.warning("seatalk.fetch_thread.failed", extra={"channel": channel}, exc_info=True)
        return [], ()
    messages = payload.get("thread_messages") or [] if isinstance(payload, dict) else []
    # Recurse: a forwarded record in the thread flattens to its leaves for text,
    # and its images/files download alongside the direct ones.
    return (
        collect_forwarded_items(messages),
        await thread_media_attachments(client, media_dir, ensure_token, messages),
    )
