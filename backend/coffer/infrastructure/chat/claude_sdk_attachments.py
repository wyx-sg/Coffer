"""Materialise turn attachments into Claude stream-json content blocks."""

from __future__ import annotations

import base64
import pathlib
from collections.abc import Sequence
from typing import Any

from coffer.domain.chat.attachment import (
    INLINE_IMAGE_MAX_BYTES,
    Attachment,
    attachment_line,
    base64_size,
    inline_image_mime,
)
from coffer.domain.turn_markers import ATTACHMENTS, ATTACHMENTS_END, heading


def _text(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def attachment_blocks(att: Attachment) -> list[dict[str, Any]]:
    """Materialise one attachment: an image the API takes inline
    (``inline_image_mime``: sniffed type, under the ceiling) as its ``#n`` caption
    followed by a base64 ``image`` block — the base64 lives only in this request —
    and anything else as its ``[Attachments]`` line with the on-disk path, which
    the agent opens with its own tools. Documents were text-extracted upstream."""
    path = pathlib.Path(att.path)
    try:
        fits = base64_size(path.stat().st_size) <= INLINE_IMAGE_MAX_BYTES
        data = path.read_bytes() if att.is_image and fits else b""
    except OSError:
        return [_text(attachment_line(att, readable=False))]
    media_type = inline_image_mime(data) if data else None
    if media_type is not None:
        encoded = base64.standard_b64encode(data).decode()
        return [
            _text(attachment_line(att, shown_inline=True)),
            {
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": encoded},
            },
        ]
    line = attachment_line(att)
    if not att.unreadable_kind:
        line += " — open it with your tools if it is relevant"
    return [_text(line)]


def attachments_content(attachments: Sequence[Attachment]) -> list[dict[str, Any]]:
    """The turn's ``[Attachments]`` block as content blocks: heading, each
    attachment, end line."""
    blocks = [_text(heading(ATTACHMENTS))]
    for att in attachments:
        blocks.extend(attachment_blocks(att))
    blocks.append(_text(heading(ATTACHMENTS_END)))
    return blocks
