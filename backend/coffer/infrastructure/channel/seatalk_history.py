"""Fetching a SeaTalk thread's own messages for turn context.

A helper module beside ``seatalk.py``, like ``seatalk_media.py`` and
``seatalk_parse.py``: the adapter keeps the port method, the work lives here so
that file stays inside the size cap.
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
) -> tuple[list[ForwardedItem], tuple[InboundAttachment, ...]]:
    """The thread's own messages, when the @mention landed inside a thread.

    Returns their flattened text AND the images/files they carry, downloaded
    (FR-029) so a picture in the thread reaches the vision agent instead of a
    dead auth-gated file link. Degrades to ``([], ())`` on ANY error so a
    transient failure never breaks the turn, which still runs on the @mention
    alone. Group-main @mentions fetch no history — that permission is
    intentionally not granted.
    """
    try:
        payload = await get(
            "/messaging/v2/group_chat/get_thread_by_thread_id",
            {"group_id": chat_id, "thread_id": thread_id, "page_size": limit},
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
