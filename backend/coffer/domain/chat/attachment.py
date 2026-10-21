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

from coffer.domain.turn_markers import ATTACHMENTS, ATTACHMENTS_END, block

#: The Messages API's ceiling for one inline base64 image, measured on the
#: encoded payload it receives. A larger image would 400 the whole turn, so it
#: reaches the agent as a path instead (see :func:`inline_image_mime`).
INLINE_IMAGE_MAX_BYTES = 5 * 1024 * 1024

#: What an attachment with no ``source`` came from.
USER_SOURCE = "the user's message"

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
    #: Its ``#n`` in the turn, which the turn text points at ("→ attachment #2");
    #: 0 when unnumbered.
    number: int = 0
    #: Where in the turn it came from, as a phrase: ``the user's message 2/2``,
    #: ``the forwarded record``, ``the quoted message``, ``a thread message``.
    #: ``""`` reads as the user's own message.
    source: str = ""

    @property
    def is_image(self) -> bool:
        return self.mime.startswith("image/")

    @property
    def unreadable_kind(self) -> str:
        """``voice`` / ``video`` for media no agent reads directly, else ``""``."""
        if self.mime.startswith("audio/"):
            return "voice"
        if self.mime.startswith("video/"):
            return "video"
        return ""


def attachment_label(att: Attachment) -> str:
    """``#2 from the user's message 2/2: report.pdf`` — how every agent adapter
    names one attachment, so the turn text's ``→ attachment #2`` resolves."""
    source = att.source or USER_SOURCE
    number = f"#{att.number} " if att.number else ""
    # A platform-supplied name: one line, so it cannot open a line of its own.
    name = " ".join("".join(" " if ch < " " else ch for ch in att.filename).split())
    return f"{number}from {source}: {name or 'file'}"


def attachment_line(att: Attachment, *, readable: bool = True, shown_inline: bool = False) -> str:
    """One line of the turn's ``[Attachments]`` block (spec channels "Hand inbound
    attachments to the turn as references"). Voice and video say plainly that the
    model cannot read them; a file that is gone says it could not be read."""
    label = attachment_label(att)
    if not readable:
        return f"{label} — could not be read (the file is no longer on disk)"
    kind = att.unreadable_kind
    if kind:
        return f"{label} — {kind}; the model cannot read it directly; file at {att.path}"
    if shown_inline:
        return f"{label} (image, shown below)"
    if att.is_image:
        return f"{label} (image, saved at {att.path})"
    return f"{label} (saved at {att.path})"


def attachments_block(lines: Sequence[str]) -> str:
    """The ``[Attachments]`` block around ``lines``; ``""`` when there are none."""
    return block(ATTACHMENTS, ATTACHMENTS_END, list(lines)) if lines else ""


def attachment_note(attachments: Sequence[Attachment]) -> str:
    """A short stand-in for a message that carries files and no text, so its
    ``[User message]`` block is not blank — ``(sent an image → attachment #2)``.
    Used for a channel's uncaptioned photo."""
    kind = "image" if all(a.is_image for a in attachments) else "file"
    if len(attachments) == 1:
        what = f"an {kind}" if kind == "image" else f"a {kind}"
    else:
        what = f"{len(attachments)} {kind}s"
    numbers = [f"#{a.number}" for a in attachments if a.number]
    if numbers and len(numbers) == len(attachments):
        noun = "attachment" if len(numbers) == 1 else "attachments"
        return f"(sent {what} → {noun} {', '.join(numbers)})"
    return f"(sent {what}: {', '.join(a.filename for a in attachments)})"


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
    "USER_SOURCE",
    "Attachment",
    "attachment_label",
    "attachment_line",
    "attachment_note",
    "attachments_block",
    "base64_size",
    "inline_image_mime",
    "sniff_image_mime",
]
