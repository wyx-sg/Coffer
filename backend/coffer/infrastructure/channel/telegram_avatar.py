"""A paired person's Telegram profile picture (spec channels "Show each paired
person's platform picture").

``getUserProfilePhotos`` lists the person's pictures newest first, each in
several sizes; the newest one's smallest size that still fills the list's
avatar is downloaded through ``getFile`` like any other file. Any bot may ask
this of a user who has written to it, which every paired person has.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from coffer.infrastructure.channel.telegram_media import download_file

__all__ = ["fetch_avatar"]

#: Telegram's sizes are 160, 320 and 640 px; the list shows the picture at a
#: few dozen, so the smallest at least this wide is the one to fetch.
_MIN_WIDTH = 96


async def fetch_avatar(
    client: httpx.AsyncClient,
    call: Callable[..., Awaitable[Any]],
    file_base: str,
    name: str,
    user_id: str,
) -> bytes | None:
    """The person's current picture, or ``None`` when they have none (or hide
    it from bots). Raises ``ChannelSendFailed`` when Telegram could not be asked."""
    result = await call("getUserProfilePhotos", user_id=user_id, limit=1)
    photos = result.get("photos") if isinstance(result, dict) else None
    if not photos or not isinstance(photos[0], list) or not photos[0]:
        return None
    sizes = sorted(
        (s for s in photos[0] if isinstance(s, dict) and s.get("file_id")),
        key=lambda s: int(s.get("width") or 0),
    )
    if not sizes:
        return None
    chosen = next((s for s in sizes if int(s.get("width") or 0) >= _MIN_WIDTH), sizes[-1])
    return await download_file(client, call, file_base, str(chosen["file_id"]), name)
