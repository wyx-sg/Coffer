"""Telegram media/attachment helpers and the bot command menu — split out of
``telegram.py`` to keep that module under the file-size limit. Pure/no-I/O
except ``default_media_dir``, which only reads an env var.
"""

from __future__ import annotations

import os
import pathlib
from collections.abc import Sequence
from typing import Any

from coffer.domain.channel.envelopes import ChoiceButton

__all__ = ["COMMANDS", "default_media_dir", "inline_keyboard", "media_specs"]

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
