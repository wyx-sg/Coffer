"""Materialise a turn attachment into a Claude stream-json content block."""

from __future__ import annotations

import base64
import pathlib
from typing import Any

from coffer.domain.chat.attachment import (
    INLINE_IMAGE_MAX_BYTES,
    Attachment,
    base64_size,
    inline_image_mime,
)


def attachment_block(att: Attachment) -> dict[str, Any]:
    """Materialise one attachment into a stream-json content block: an image the
    API takes inline (``inline_image_mime``: sniffed type, under the ceiling) as
    a base64 ``image`` block — the base64 lives only in this request — and
    anything else as a text pointer to its on-disk path, which the agent opens
    with its own tools. Documents were text-extracted upstream."""
    path = pathlib.Path(att.path)
    try:
        fits = base64_size(path.stat().st_size) <= INLINE_IMAGE_MAX_BYTES
        data = path.read_bytes() if att.is_image and fits else b""
    except OSError:
        return {"type": "text", "text": f"[Attached file '{att.filename}' could not be read]"}
    media_type = inline_image_mime(data) if data else None
    if media_type is not None:
        encoded = base64.standard_b64encode(data).decode()
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": encoded},
        }
    return {
        "type": "text",
        "text": (
            f"[The user attached a file '{att.filename}', saved at {att.path}. "
            "Open it with your tools if it is relevant.]"
        ),
    }
