"""Which SeaTalk message entries carry downloadable media, and under what name.

Pure — no I/O. Shared by the downloader (``seatalk_media``) and the record
flattener (``seatalk_parse``): both walk the same entries, and the file link this
module picks is the key (``InboundAttachment.ref`` / ``ForwardedItem.media_ref``)
that lets a flattened line point at the file it downloaded.
"""

from __future__ import annotations

import mimetypes
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

__all__ = ["MediaRef", "collect_image_urls", "collect_media", "media_ref", "mime_from_name"]


@dataclass(frozen=True)
class MediaRef:
    """One downloadable SeaTalk media item: its auth-gated file URL plus the
    filename and (best-effort) mime to save it under, so the agent sees a real
    name/type instead of a uuid. ``mime`` may be ``None`` (resolve it from the
    download's content-type). ``kind`` distinguishes an image (vision-inlined)
    from a file/generic attachment and lets :func:`collect_image_urls` filter."""

    url: str
    filename: str
    mime: str | None = None
    kind: str = "media"  # "image" | "file" | "media" (generic best-effort)


def collect_media(message: dict[str, Any]) -> list[MediaRef]:
    """Every downloadable SeaTalk media item reachable from one message (spec channels/seatalk
    "Download every inbound SeaTalk media type").

    A directly-sent image carries ``message.image.content``; a file/document
    carries ``message.file.content`` + ``message.file.filename``; any other tag
    whose sub-dict holds a file-URL ``content`` (voice/video/audio, best effort)
    is picked up generically. A forwarded chat record nests media messages
    (possibly several levels deep) — recurse the same way the text flattener does
    so a file buried in a forwarded record is still fetched.
    """
    tag = str(message.get("tag", ""))
    if tag == "combined_forwarded_chat_history":
        content = (message.get("combined_forwarded_chat_history") or {}).get("content") or []
        return _media_from_content(content)
    ref = media_ref(message, tag)
    return [ref] if ref is not None else []


def collect_image_urls(message: dict[str, Any]) -> list[str]:
    """Every downloadable SeaTalk *image* URL reachable from one message.

    Retained for its callers/tests; a thin image-only view over
    :func:`collect_media` so the recursion lives in one place."""
    return [ref.url for ref in collect_media(message) if ref.kind == "image"]


def media_ref(entry: dict[str, Any], tag: str) -> MediaRef | None:
    """One :class:`MediaRef` for a single (non-forwarded) message, or ``None``
    when it carries nothing downloadable."""
    if tag == "image":
        url = (entry.get("image") or {}).get("content")
        if isinstance(url, str) and url:
            return MediaRef(url=url, filename="photo", mime=None, kind="image")
        return None
    if tag == "file":
        body = entry.get("file") or {}
        url = body.get("content")
        if isinstance(url, str) and url:
            name = str(body.get("filename") or "file")
            return MediaRef(url=url, filename=name, mime=mime_from_name(name), kind="file")
        return None
    # Generic best-effort (voice/video/audio, unverified shapes): any other tag
    # whose sub-dict holds a file-URL ``content``.
    body = entry.get(tag)
    if isinstance(body, dict):
        url = body.get("content")
        if isinstance(url, str) and _is_file_url(url):
            name = str(body.get("filename") or tag)
            return MediaRef(url=url, filename=name, mime=None, kind="media")
    return None


def _media_from_content(content: Sequence[Any]) -> list[MediaRef]:
    refs: list[MediaRef] = []
    for entry in content:
        if not isinstance(entry, dict):
            continue
        tag = str(entry.get("tag", ""))
        if tag == "combined_forwarded_chat_history":
            nested = (entry.get("combined_forwarded_chat_history") or {}).get("content") or []
            refs.extend(_media_from_content(nested))
        else:
            ref = media_ref(entry, tag)
            if ref is not None:
                refs.append(ref)
    return refs


def _is_file_url(url: str) -> bool:
    """A SeaTalk auth-gated file link (``.../messaging/v2/file/<id>``). Kept
    lenient (``/file/`` present) so a forwarded record's media still matches."""
    return url.startswith("http") and "/file/" in url


def mime_from_name(name: str) -> str:
    """A non-``None`` mime guessed from a filename's extension — falling back to
    ``application/octet-stream`` so a downloaded *file* never inherits the
    download's (image) content-type and is misread as a picture."""
    return mimetypes.guess_type(name)[0] or "application/octet-stream"
