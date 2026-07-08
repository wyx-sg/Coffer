"""SeaTalk inbound media: find the downloadable image URLs on a message
(a directly-sent image, or every image nested in a forwarded chat record) and
fetch them, authenticated, into local attachments the agent can actually see.

SeaTalk delivers images as authenticated file links
(``https://openapi.seatalk.io/messaging/v2/file/<id>[?seq=N]``) — the agent
can't open them, so the transport must download the bytes with the app token
and hand them to the turn as attachments. Split out of ``seatalk.py`` (mirroring
``telegram_media.py``) to keep that module under the file-size limit.
"""

from __future__ import annotations

import logging
import os
import pathlib
import uuid
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

import httpx

from coffer.domain.channel.envelopes import InboundAttachment

__all__ = ["collect_image_urls", "default_media_dir", "media_attachments"]

_logger = logging.getLogger(__name__)

# content-type → file suffix for the saved attachment (best-effort; SeaTalk
# images are png/jpeg in practice).
_SUFFIX_BY_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def default_media_dir() -> pathlib.Path:
    """``~/.coffer/channel-media`` — where inbound images are saved. ``HOME`` is
    honored (not ``Path.home()``) so tests can redirect it to a tmp dir."""
    home = pathlib.Path(os.environ.get("HOME") or "~").expanduser()
    return home / ".coffer" / "channel-media"


def collect_image_urls(message: dict[str, Any]) -> list[str]:
    """Every downloadable SeaTalk image URL reachable from one message.

    A directly-sent image carries ``message.image.content``; a forwarded chat
    record nests image messages (possibly several levels deep) — recurse the
    same way the text flattener does so a chart buried in a forwarded thread is
    still fetched.
    """
    tag = str(message.get("tag", ""))
    if tag == "image":
        url = (message.get("image") or {}).get("content")
        return [url] if isinstance(url, str) and url else []
    if tag == "combined_forwarded_chat_history":
        content = (message.get("combined_forwarded_chat_history") or {}).get("content") or []
        return _urls_from_content(content)
    return []


def _urls_from_content(content: Sequence[Any]) -> list[str]:
    urls: list[str] = []
    for entry in content:
        if not isinstance(entry, dict):
            continue
        tag = str(entry.get("tag", ""))
        if tag == "image":
            url = (entry.get("image") or {}).get("content")
            if isinstance(url, str) and url:
                urls.append(url)
        elif tag == "combined_forwarded_chat_history":
            nested = (entry.get("combined_forwarded_chat_history") or {}).get("content") or []
            urls.extend(_urls_from_content(nested))
    return urls


async def media_attachments(
    client: httpx.AsyncClient,
    media_dir: pathlib.Path,
    ensure_token: Callable[[], Awaitable[str]],
    message: dict[str, Any],
) -> tuple[InboundAttachment, ...]:
    """Download every image on ``message`` (direct or forwarded) as an
    attachment. Fetches the app token only when there is something to download;
    a single failed download is skipped (logged), never wedging the message."""
    urls = collect_image_urls(message)
    if not urls:
        return ()
    token = await ensure_token()
    media_dir.mkdir(parents=True, exist_ok=True)
    headers = {"Authorization": f"Bearer {token}"}
    out: list[InboundAttachment] = []
    for url in urls:
        try:
            response = await client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()
        except Exception:
            _logger.warning("seatalk.media.download_failed", exc_info=True)
            continue
        mime = (response.headers.get("content-type") or "image/jpeg").split(";")[0].strip()
        name = f"{uuid.uuid4().hex}{_SUFFIX_BY_MIME.get(mime, '.jpg')}"
        (media_dir / name).write_bytes(response.content)
        out.append(InboundAttachment(path=str(media_dir / name), mime=mime, filename=name))
    return tuple(out)
