"""SeaTalk inbound media: find every downloadable file URL on a message
(a directly-sent image/file, or any media nested in a forwarded chat record) and
fetch it, authenticated, into a local attachment the agent can actually see.

SeaTalk delivers media as authenticated file links
(``https://openapi.seatalk.io/messaging/v2/file/<id>[?seq=N]``) — the agent
can't open them, so the transport must download the bytes with the app token
and hand them to the turn as attachments. Images, files/documents, and (best
effort) voice/video all take this path (FR-028), so a directly-sent PDF or voice
memo drives a turn like a photo does. Split out of ``seatalk.py`` (mirroring
``telegram_media.py``) to keep that module under the file-size limit.
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import os
import pathlib
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from coffer.domain.channel.envelopes import InboundAttachment

__all__ = [
    "MediaRef",
    "build_outbound_media_message",
    "collect_image_urls",
    "collect_media",
    "default_media_dir",
    "media_attachments",
    "send_outbound_media",
    "thread_media_attachments",
]

_logger = logging.getLogger(__name__)

# Outbound: an image extension goes as a SeaTalk ``image`` message (inline
# preview); anything else as a ``file`` message (mirrors the inbound suffix map).
_OUTBOUND_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})


def build_outbound_media_message(path: str) -> dict[str, Any]:
    """Build the SeaTalk outbound message body for a local file.

    An image (by extension) becomes ``{tag: "image", image: {content: <b64>}}``;
    any other file becomes ``{tag: "file", file: {filename, content: <b64>}}``.
    ``content`` is base64 of the raw bytes — unlike an *inbound* image, whose
    ``content`` is an auth-gated download URL. Pure (reads the file, no network)
    so it stays out of the size-capped ``seatalk.py``."""
    p = pathlib.Path(path)
    content = base64.b64encode(p.read_bytes()).decode("ascii")
    if p.suffix.lower() in _OUTBOUND_IMAGE_SUFFIXES:
        return {"tag": "image", "image": {"content": content}}
    return {"tag": "file", "file": {"filename": p.name, "content": content}}


async def send_outbound_media(
    send: Callable[[str, dict[str, Any], str, str], Awaitable[Any]],
    chat_id: str,
    path: str,
    *,
    caption: str | None,
    thread_id: str,
    chat_kind: str,
) -> str:
    """Upload one local file, then its caption, through ``send`` (the adapter's
    ``_send(chat_id, message, thread_id, chat_kind)`` router — so both land in
    the same chat_kind + thread the turn came from, FR-031). SeaTalk file
    messages carry no caption field, so a non-empty caption follows as a short
    threaded text message. Returns the last platform message id."""
    result = await send(chat_id, build_outbound_media_message(path), thread_id, chat_kind)
    last = str(result.get("message_id", ""))
    if caption:
        follow = await send(
            chat_id,
            {"tag": "text", "text": {"format": 1, "content": caption}},
            thread_id,
            chat_kind,
        )
        last = str(follow.get("message_id", "")) or last
    return last


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
    """Every downloadable SeaTalk media item reachable from one message (FR-028).

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
    ref = _media_ref(message, tag)
    return [ref] if ref is not None else []


def collect_image_urls(message: dict[str, Any]) -> list[str]:
    """Every downloadable SeaTalk *image* URL reachable from one message.

    Retained for its callers/tests; a thin image-only view over
    :func:`collect_media` so the recursion lives in one place."""
    return [ref.url for ref in collect_media(message) if ref.kind == "image"]


def _media_ref(entry: dict[str, Any], tag: str) -> MediaRef | None:
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
            return MediaRef(url=url, filename=name, mime=_mime_from_name(name), kind="file")
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
            ref = _media_ref(entry, tag)
            if ref is not None:
                refs.append(ref)
    return refs


def _is_file_url(url: str) -> bool:
    """A SeaTalk auth-gated file link (``.../messaging/v2/file/<id>``). Kept
    lenient (``/file/`` present) so a forwarded record's media still matches."""
    return url.startswith("http") and "/file/" in url


def _mime_from_name(name: str) -> str:
    """A non-``None`` mime guessed from a filename's extension — falling back to
    ``application/octet-stream`` so a downloaded *file* never inherits the
    download's (image) content-type and is misread as a picture."""
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def _extension_for_mime(mime: str) -> str:
    return _SUFFIX_BY_MIME.get(mime) or mimetypes.guess_extension(mime) or ""


def _safe_filename(name: str, mime: str) -> str:
    """A path-separator-free attachment name, with an extension appended (from
    the mime) when the original has none — so an image saved as ``photo`` still
    reads as ``photo.png`` while ``create_acc.sh`` is preserved verbatim."""
    base = pathlib.PureWindowsPath(pathlib.PurePosixPath(name).name).name or "file"
    if not pathlib.Path(base).suffix:
        base = f"{base}{_extension_for_mime(mime)}"
    return base


async def media_attachments(
    client: httpx.AsyncClient,
    media_dir: pathlib.Path,
    ensure_token: Callable[[], Awaitable[str]],
    message: dict[str, Any],
) -> tuple[InboundAttachment, ...]:
    """Download every media item on ``message`` (image/file/generic, direct or
    forwarded) as an attachment (FR-028). Fetches the app token only when there
    is something to download; a single failed download is skipped (logged),
    never wedging the message."""
    refs = collect_media(message)
    if not refs:
        return ()
    token = await ensure_token()
    return await _download(client, media_dir, token, refs)


async def thread_media_attachments(
    client: httpx.AsyncClient,
    media_dir: pathlib.Path,
    ensure_token: Callable[[], Awaitable[str]],
    messages: Sequence[dict[str, Any]],
) -> tuple[InboundAttachment, ...]:
    """Download every media item carried by a thread's own messages (FR-029) so
    an in-thread @mention grounds the turn on the real pictures/files, not the
    dead auth-gated links a text flatten would leave behind. Collects refs
    across ALL ``messages`` — recursing forwarded records within each via
    :func:`collect_media` — and fetches them with the same authenticated
    download the direct-message path uses. Fetches the token only when there is
    something to download; each failed download is skipped, never wedging the
    turn."""
    refs: list[MediaRef] = []
    for message in messages:
        if isinstance(message, dict):
            refs.extend(collect_media(message))
    if not refs:
        return ()
    token = await ensure_token()
    return await _download(client, media_dir, token, refs)


async def _download(
    client: httpx.AsyncClient,
    media_dir: pathlib.Path,
    token: str,
    refs: Sequence[MediaRef],
) -> tuple[InboundAttachment, ...]:
    """Fetch each :class:`MediaRef` (authenticated) into ``media_dir`` as an
    attachment. The saved file keeps the ref's real (sanitised) filename so the
    agent sees ``create_acc.sh``, not a uuid; the on-disk name is uuid-unique.
    The mime is the ref's own if set, else the download's content-type, else a
    guess from the filename, else ``application/octet-stream``. A single failed
    download is skipped (logged), never wedging the caller — shared by the
    direct-message and thread-history paths."""
    media_dir.mkdir(parents=True, exist_ok=True)
    headers = {"Authorization": f"Bearer {token}"}
    out: list[InboundAttachment] = []
    for ref in refs:
        try:
            response = await client.get(ref.url, headers=headers, follow_redirects=True)
            response.raise_for_status()
        except Exception:
            _logger.warning("seatalk.media.download_failed", exc_info=True)
            continue
        content_type = (response.headers.get("content-type") or "").split(";")[0].strip()
        mime = ref.mime or content_type or _mime_from_name(ref.filename)
        filename = _safe_filename(ref.filename, mime)
        disk_name = f"{uuid.uuid4().hex}{pathlib.Path(filename).suffix}"
        (media_dir / disk_name).write_bytes(response.content)
        out.append(InboundAttachment(path=str(media_dir / disk_name), mime=mime, filename=filename))
    return tuple(out)
