"""Telegram media/attachment helpers and the bot command menu — split out of
``telegram.py`` to keep that module under the file-size limit. Mostly pure; the
outbound ``upload_media`` and the env-reading ``default_media_dir`` are the only
I/O.
"""

from __future__ import annotations

import logging
import os
import pathlib
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from coffer.domain.channel.envelopes import ChoiceButton, InboundAttachment, SentMessage
from coffer.domain.channel.errors import ChannelSendFailed

__all__ = [
    "FetchedMedia",
    "default_media_dir",
    "download_attachments",
    "inline_keyboard",
    "media_specs",
    "routing_params",
    "upload_media",
]

#: Bots may only download files up to this size (Bot API ``getFile``). A larger
#: one is not a transient failure — it can never be fetched — so FR-067 says so
#: in the chat instead of dropping it silently.
_DOWNLOAD_LIMIT_BYTES = 20 * 1024 * 1024

_logger = logging.getLogger(__name__)


def default_media_dir() -> pathlib.Path:
    """``~/.coffer/channel-media`` — where inbound photos/files/voice are saved.

    ``HOME`` is honored (not ``Path.home()``) so tests redirect it to a tmp dir.
    """
    home = pathlib.Path(os.environ.get("HOME") or "~").expanduser()
    return home / ".coffer" / "channel-media"


#: Every non-photo media field a Telegram message can carry, with the mime and
#: filename to fall back on when the payload names neither (FR-067). Ordered so
#: a message carrying several lands its attachments predictably.
_MEDIA_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("document", "application/octet-stream", "file"),
    ("voice", "audio/ogg", "voice.ogg"),
    ("audio", "audio/mpeg", "audio"),
    ("video", "video/mp4", "video.mp4"),
    # A GIF/looping clip arrives as ``animation`` — Telegram sends it alongside
    # a ``document`` twin, which media_specs de-duplicates by file_id below.
    ("animation", "video/mp4", "animation.mp4"),
    # A round video message: ordinary media, no filename of its own.
    ("video_note", "video/mp4", "video_note.mp4"),
    # A sticker is a real picture the user chose deliberately. Without this a
    # sticker-only message reached the agent as an empty turn.
    ("sticker", "image/webp", "sticker.webp"),
)


def media_specs(message: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Extract ``(file_id, mime, filename)`` for each attachment on a Telegram
    message — largest photo size, plus every other media field the platform can
    attach (FR-067). Absent media yields nothing (a plain text message)."""
    specs: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    photo = message.get("photo")
    if isinstance(photo, list) and photo:
        # PhotoSizes are ordered small→large; the last is the highest resolution.
        largest = photo[-1]
        if isinstance(largest, dict) and largest.get("file_id"):
            specs.append((str(largest["file_id"]), "image/jpeg", "photo.jpg"))
            seen.add(str(largest["file_id"]))
    for key, default_mime, default_name in _MEDIA_FIELDS:
        item = message.get(key)
        if not (isinstance(item, dict) and item.get("file_id")):
            continue
        file_id = str(item["file_id"])
        if file_id in seen:
            continue  # the animation/document twin of one upload
        seen.add(file_id)
        mime = str(item.get("mime_type") or default_mime)
        filename = str(item.get("file_name") or default_name)
        specs.append((file_id, mime, filename))
    return specs


def _oversized(message: dict[str, Any]) -> list[str]:
    """Human labels for attachments too large for a bot to download (FR-067).

    ``file_size`` rides on the media object itself, so the cap is known before
    ``getFile`` is ever called — the user can be told exactly which file was
    left behind instead of watching an answer that never mentions it.
    """
    labels: list[str] = []
    for key, _mime, default_name in _MEDIA_FIELDS:
        item = message.get(key)
        if not isinstance(item, dict):
            continue
        size = item.get("file_size")
        if isinstance(size, int) and size > _DOWNLOAD_LIMIT_BYTES:
            labels.append(str(item.get("file_name") or default_name))
    return labels


def inline_keyboard(buttons: Sequence[ChoiceButton]) -> dict[str, Any]:
    """One button per row (selection menus stay readable on a phone).

    FR-069: the option already in effect is rendered with the platform's own
    button states — coloured as the successful choice and disabled — so the card
    stops offering something that tapping cannot change. Both fields arrived in
    Bot API 10.3; an older client ignores what it does not know and shows an
    ordinary button, which is exactly the old behaviour.
    """
    return {"inline_keyboard": [[_button(b)] for b in buttons]}


def _button(button: ChoiceButton) -> dict[str, Any]:
    entry: dict[str, Any] = {"text": button.label, "callback_data": button.value}
    if button.selected:
        entry["style"] = "success"
        entry["disabled"] = {}
    return entry


def routing_params(thread_id: str = "", reply_to_message_id: str = "") -> dict[str, Any]:
    """The parameters that place a message: its forum topic and the message it
    answers (FR-068).

    ``allow_sending_without_reply`` matters: the message being answered can be
    gone by the time the turn finishes (deleted, or expired in a topic), and a
    reply that fails because its target vanished would lose the whole answer.
    """
    extra: dict[str, Any] = {}
    if thread_id:
        extra["message_thread_id"] = int(thread_id)
    if reply_to_message_id:
        extra["reply_parameters"] = {
            "message_id": int(reply_to_message_id),
            "allow_sending_without_reply": True,
        }
    return extra


async def upload_media(
    client: httpx.AsyncClient,
    base: str,
    name: str,
    chat_id: str,
    path: str,
    *,
    caption: str | None,
    as_photo: bool,
    thread_id: str,
) -> SentMessage:
    """Upload a local file via ``sendPhoto`` (inline image) or ``sendDocument``
    (multipart, so the platform stores + serves the bytes). A non-empty
    ``thread_id`` posts into that forum topic (FR-031), mirroring send_text.
    Split out of ``telegram.py`` to keep it under the file-size limit."""
    method, field = ("sendPhoto", "photo") if as_photo else ("sendDocument", "document")
    file = pathlib.Path(path)
    data: dict[str, str] = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption
    if thread_id:
        data["message_thread_id"] = thread_id
    try:
        response = await client.post(
            f"{base}/{method}", data=data, files={field: (file.name, file.read_bytes())}
        )
    except httpx.HTTPError as e:
        raise ChannelSendFailed(name, type(e).__name__) from e
    try:
        payload = response.json()
    except ValueError as e:
        raise ChannelSendFailed(
            name,
            f"{method}: non-JSON response ({response.status_code})",
            api_rejected=True,
            status=response.status_code,
        ) from e
    if not isinstance(payload, dict) or not payload.get("ok", False):
        description = payload.get("description", "") if isinstance(payload, dict) else ""
        raise ChannelSendFailed(
            name,
            f"{method}: {description or response.status_code}",
            api_rejected=True,
            status=response.status_code,
        )
    result = payload.get("result") or {}
    return SentMessage(message_id=str(result.get("message_id", "")))


@dataclass(frozen=True)
class FetchedMedia:
    """What came off one inbound message: the attachments that downloaded, and
    human-readable notes about the ones that did not.

    FR-067: a file a bot may never download is not a silent no-op — the note
    rides into the turn text so the answer can acknowledge it.
    """

    attachments: tuple[InboundAttachment, ...] = ()
    notes: tuple[str, ...] = ()


async def download_attachments(
    client: httpx.AsyncClient,
    call: Callable[..., Awaitable[Any]],
    file_base: str,
    media_dir: pathlib.Path,
    name: str,
    message: dict[str, Any],
) -> FetchedMedia:
    """Download each attachment on ``message`` to ``media_dir``. Best-effort: a
    download that fails is skipped (logged) and noted, never wedging the
    message — the text/caption still drives a turn."""
    out: list[InboundAttachment] = []
    notes: list[str] = [
        f"[attachment '{label}' is larger than the {_DOWNLOAD_LIMIT_BYTES // (1024 * 1024)} MB "
        "a bot may download — it did not reach the agent]"
        for label in _oversized(message)
    ]
    for file_id, mime, filename in media_specs(message):
        try:
            data = await _download_file(client, call, file_base, file_id)
        except Exception:
            _logger.warning(
                "telegram.media.download_failed", extra={"channel": name}, exc_info=True
            )
            notes.append(f"[attachment '{filename}' could not be downloaded]")
            continue
        if data is None:
            notes.append(f"[attachment '{filename}' could not be downloaded]")
            continue
        out.append(
            InboundAttachment(
                path=_save_media(media_dir, data, filename), mime=mime, filename=filename
            )
        )
    return FetchedMedia(attachments=tuple(out), notes=tuple(notes))


async def _download_file(
    client: httpx.AsyncClient,
    call: Callable[..., Awaitable[Any]],
    file_base: str,
    file_id: str,
) -> bytes | None:
    """``getFile`` → download the bytes from the file endpoint."""
    info = await call("getFile", file_id=file_id)
    file_path = info.get("file_path") if isinstance(info, dict) else None
    if not file_path:
        return None
    response = await client.get(f"{file_base}/{file_path}")
    response.raise_for_status()
    return response.content


def _save_media(media_dir: pathlib.Path, data: bytes, filename: str) -> str:
    """Write bytes under the media dir with a unique name; return the path."""
    media_dir.mkdir(parents=True, exist_ok=True)
    path = media_dir / f"{uuid.uuid4().hex}{pathlib.Path(filename).suffix}"
    path.write_bytes(data)
    return str(path)
