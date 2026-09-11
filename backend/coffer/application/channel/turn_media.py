"""The reply-file sentinel: how an agent hands the user a real file.

Split out of ``turn_render`` (behaviour-preserving) so the renderer module
holds only the turn-event → chat-traffic path. The agent opts in by writing a
line-anchored ``MEDIA:/absolute/path`` (optionally ``| caption``); ordinary
prose — including a legitimate markdown image the agent wrote only to
*reference* a file — never uploads anything.
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import re
from collections.abc import Sequence

from coffer.application.channel.ports import ChannelAdapter
from coffer.domain.chat.attachment import Attachment

#: A line-anchored ``MEDIA:/abs/path`` sentinel, with an optional ``| caption``
#: after a pipe. Unlike markdown image syntax this never collides with prose.
#: The path group allows spaces (absolute macOS paths routinely contain them).
_MEDIA_MARKER = re.compile(
    r"^[ \t]*MEDIA:[ \t]*(?P<path>[^|\n]*?)[ \t]*(?:\|[ \t]*(?P<caption>[^\n]*?))?[ \t]*$",
    re.MULTILINE,
)
_MEDIA_MAX_BYTES = 50 * 1024 * 1024  # Telegram sendDocument caps at 50 MB
_PHOTO_MAX_BYTES = 10 * 1024 * 1024  # sendPhoto caps at 10 MB — larger images go as documents
_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})


def attachment_note(attachments: Sequence[Attachment]) -> str:
    """A short stand-in text for a media message with no caption, so the persisted
    user turn is not blank (the bytes reach the agent out-of-band)."""
    names = ", ".join(a.filename for a in attachments)
    kind = "image" if all(a.is_image for a in attachments) else "file"
    plural = "s" if len(attachments) != 1 else ""
    return f"(sent {len(attachments)} {kind}{plural}: {names})"


def _is_image_path(path: str) -> bool:
    return pathlib.Path(path).suffix.lower() in _IMAGE_SUFFIXES


def _deliverable(path: str) -> bool:
    """A marker is honoured only for an absolute path to a real, sane-sized file —
    so a relative path or a bare mention in prose never uploads by accident."""
    if not os.path.isabs(path):
        return False
    try:
        p = pathlib.Path(path)
        return bool(p.is_file() and p.stat().st_size <= _MEDIA_MAX_BYTES)
    except OSError:
        return False


async def deliver_media(
    adapter: ChannelAdapter,
    chat_id: str,
    text: str,
    *,
    thread_id: str = "",
    chat_kind: str = "direct",
) -> tuple[str, int]:
    """Handle each ``MEDIA:`` sentinel line whose file exists; return the text
    with the handled lines removed and how many files were uploaded.

    On a media-capable channel the file is uploaded and the sentinel line
    stripped; on a channel without file support the line is replaced with a plain
    note so the user never sees a raw local path for a file that was never
    delivered.
    """
    supports = adapter.capabilities.supports_media
    sent = 0
    out = text
    for match in _MEDIA_MARKER.finditer(text):
        path = (match.group("path") or "").strip()
        caption = (match.group("caption") or "").strip()
        if not _deliverable(path):
            continue  # not a real absolute file — leave the line untouched
        if not supports:
            label = caption or pathlib.Path(path).name
            out = out.replace(
                match.group(0),
                f"(couldn't send '{label}' — this channel has no file support)",
                1,
            ).strip()
            continue
        try:
            # sendPhoto caps at 10 MB; a larger image goes as a document.
            as_photo = (
                _is_image_path(path) and pathlib.Path(path).stat().st_size <= _PHOTO_MAX_BYTES
            )
            if adapter.capabilities.supports_typing:
                # An upload of any size shows a busy signal; saying WHAT it is
                # busy with beats claiming to type while a file goes up.
                with contextlib.suppress(Exception):
                    await adapter.send_typing(
                        chat_id, action="upload_photo" if as_photo else "upload_document"
                    )
            await adapter.send_media(
                chat_id,
                path,
                caption=caption or None,
                as_photo=as_photo,
                thread_id=thread_id,
                chat_kind=chat_kind,
            )
        except Exception:
            continue  # leave the line in place so the intent is still visible
        sent += 1
        out = out.replace(match.group(0), "", 1).strip()
    return out, sent
