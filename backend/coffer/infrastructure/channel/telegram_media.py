"""Telegram media/attachment helpers and the bot command menu — split out of
``telegram.py`` to keep that module under the file-size limit. Mostly pure; the
outbound ``upload_media`` and the env-reading ``default_media_dir`` are the only
I/O.
"""

from __future__ import annotations

import os
import pathlib
from collections.abc import Sequence
from typing import Any

import httpx

from coffer.domain.channel.envelopes import ChoiceButton, SentMessage
from coffer.domain.channel.errors import ChannelSendFailed

__all__ = [
    "COMMANDS",
    "default_media_dir",
    "inline_keyboard",
    "media_specs",
    "upload_media",
]

COMMANDS = [
    {"command": "new", "description": "Start a fresh conversation"},
    {"command": "stop", "description": "Interrupt the running turn"},
    {"command": "status", "description": "Conversation and turn state"},
    {"command": "help", "description": "List commands"},
]


def default_media_dir() -> pathlib.Path:
    """``~/.coffer/channel-media`` — where inbound photos/files/voice are saved.

    ``HOME`` is honored (not ``Path.home()``) so tests redirect it to a tmp dir.
    """
    home = pathlib.Path(os.environ.get("HOME") or "~").expanduser()
    return home / ".coffer" / "channel-media"


def media_specs(message: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Extract ``(file_id, mime, filename)`` for each attachment on a Telegram
    message — largest photo size, plus any document/voice/audio/video. Unknown
    or absent media yields nothing (a plain text message)."""
    specs: list[tuple[str, str, str]] = []
    photo = message.get("photo")
    if isinstance(photo, list) and photo:
        # PhotoSizes are ordered small→large; the last is the highest resolution.
        largest = photo[-1]
        if isinstance(largest, dict) and largest.get("file_id"):
            specs.append((str(largest["file_id"]), "image/jpeg", "photo.jpg"))
    for key, default_mime, default_name in (
        ("document", "application/octet-stream", "file"),
        ("voice", "audio/ogg", "voice.ogg"),
        ("audio", "audio/mpeg", "audio"),
        ("video", "video/mp4", "video.mp4"),
    ):
        item = message.get(key)
        if isinstance(item, dict) and item.get("file_id"):
            mime = str(item.get("mime_type") or default_mime)
            filename = str(item.get("file_name") or default_name)
            specs.append((str(item["file_id"]), mime, filename))
    return specs


def inline_keyboard(buttons: Sequence[ChoiceButton]) -> dict[str, Any]:
    """One button per row (selection menus stay readable on a phone)."""
    return {"inline_keyboard": [[{"text": b.label, "callback_data": b.value}] for b in buttons]}


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
