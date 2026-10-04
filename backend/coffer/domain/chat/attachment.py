"""A user-supplied attachment referenced by local path (spec channels).

The bytes live on disk — downloaded from a channel into
``~/.coffer/content/channel-media`` — never inline in the chat DB. Each agent
adapter *materialises* the reference in its own native shape at send time: a
vision agent inlines an image content block (base64 read from ``path``), a
path-native agent (Codex) receives the path. See the channel-attachments ADR.

This module also owns the rule for which images may travel inline
(:func:`inline_image_mime`): an image's type is what its bytes prove, never what
a channel or a filename claimed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

#: The Messages API's ceiling for one inline base64 image, measured on the
#: encoded payload it receives. A larger image would 400 the whole turn, so it
#: reaches the agent as a path instead (see :func:`inline_image_mime`).
INLINE_IMAGE_MAX_BYTES = 5 * 1024 * 1024

#: Document mime types extracted to text for every agent (spec chat "Extract
#: document attachments to text"). Images, audio and plain text/code are not
#: documents: an agent reads a path to those fine, and an image belongs on the
#: vision path.
DOCUMENT_MIMES = frozenset(
    {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/rtf",
        "text/rtf",
        "application/epub+zip",
        "text/csv",
    }
)

#: Extension fallback for when a sender hands over a generic mime (e.g.
#: ``application/octet-stream``) but a document filename.
DOCUMENT_EXTENSIONS = frozenset(
    {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".rtf", ".epub", ".csv"}
)


@dataclass(frozen=True)
class Attachment:
    """One file handed to an agent for a turn — a path plus how to read it."""

    path: str  # absolute local path to the bytes
    mime: str  # e.g. "image/jpeg", "application/pdf", "audio/ogg"
    filename: str  # best-effort original name, for display / the agent's benefit

    @property
    def is_image(self) -> bool:
        return self.mime.startswith("image/")


def attachment_note(attachments: Sequence[Attachment]) -> str:
    """A short stand-in text for a message that carries files and no text, so
    the turn is not blank — an agent's request cannot hold an empty text block.
    Used for a channel's uncaptioned photo."""
    names = ", ".join(a.filename for a in attachments)
    kind = "image" if all(a.is_image for a in attachments) else "file"
    plural = "s" if len(attachments) != 1 else ""
    return f"(sent {len(attachments)} {kind}{plural}: {names})"


def sniff_image_mime(data: bytes) -> str | None:
    """The image type ``data``'s magic bytes prove — PNG, JPEG, GIF or WEBP, the
    formats the Messages API takes inline — or ``None`` for anything else."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def base64_size(size: int) -> int:
    """How many bytes ``size`` raw bytes occupy once base64-encoded."""
    return 4 * ((size + 2) // 3)


def inline_image_mime(data: bytes) -> str | None:
    """The media type to send ``data`` under as an inline image block, or
    ``None`` when it must reach the agent as a path instead: its bytes are not a
    format the API takes inline, or it is over :data:`INLINE_IMAGE_MAX_BYTES`
    once encoded. Channel media passes through here."""
    if base64_size(len(data)) > INLINE_IMAGE_MAX_BYTES:
        return None
    return sniff_image_mime(data)


__all__ = [
    "DOCUMENT_EXTENSIONS",
    "DOCUMENT_MIMES",
    "INLINE_IMAGE_MAX_BYTES",
    "Attachment",
    "attachment_note",
    "base64_size",
    "inline_image_mime",
    "sniff_image_mime",
]
