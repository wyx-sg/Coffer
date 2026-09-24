"""A user-supplied attachment referenced by local path (spec chat, spec channels).

The bytes live on disk — downloaded from a channel into ``~/.coffer/channel-media``
or uploaded from the web Chat page into ``~/.coffer/chat-media`` — never inline in
the chat DB, so conversation history stays small and the same reference works for
any modality. Each agent adapter *materialises* the reference in its own native
shape at send time: a vision agent inlines an image content block (base64 read
from ``path``), a path-native agent (Codex) receives the path. See the
channel-attachments and chat-attachment-uploads ADRs.

This module also owns the pure rules for what the web composer may upload: the
size ceiling, the per-message count, and which types are accepted
(:func:`upload_mime`) — and the rule for which images may travel inline
(:func:`inline_image_mime`): an image's type is what its bytes prove, never what
a browser or a filename claimed.
"""

from __future__ import annotations

import pathlib
import re
from collections.abc import Sequence
from dataclasses import dataclass

#: One uploaded file's ceiling. 20 MB is the bound a document passed hand-to-hand
#: already has in Coffer — the knowledge upload's ``MAX_UPLOAD_BYTES`` and
#: Telegram's bot-API download cap a channel attachment lives under — so a file
#: attached on the page and one sent from the phone meet the same ceiling.
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024

#: The Messages API's ceiling for one inline base64 image, measured on the
#: encoded payload it receives. A larger image would 400 the whole turn, so it
#: reaches the agent as a path instead (see :func:`inline_image_mime`).
INLINE_IMAGE_MAX_BYTES = 5 * 1024 * 1024

#: The generic type a file is stored under when it claimed to be an image but its
#: bytes are none of the formats :func:`sniff_image_mime` recognises.
GENERIC_MIME = "application/octet-stream"

#: How many uploaded files one message may carry.
MAX_ATTACHMENTS_PER_MESSAGE = 10

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

#: A fixed extension → mime table for the accepted non-text families. Fixed on
#: purpose: the stdlib ``mimetypes`` reads the host's mime files, so the same
#: upload would be accepted on one machine and refused on another.
_EXTENSION_MIMES: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".rtf": "application/rtf",
    ".epub": "application/epub+zip",
    ".csv": "text/csv",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".opus": "audio/opus",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
}

#: An upload id is 32 lowercase hex characters — anything else never names a
#: file, which is what keeps an id from being a path.
_UPLOAD_ID = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class Attachment:
    """One file handed to an agent for a turn — a path plus how to read it."""

    path: str  # absolute local path to the bytes
    mime: str  # e.g. "image/jpeg", "application/pdf", "audio/ogg"
    filename: str  # best-effort original name, for display / the agent's benefit

    @property
    def is_image(self) -> bool:
        return self.mime.startswith("image/")


@dataclass(frozen=True)
class UploadedAttachment:
    """A file uploaded from the web composer, waiting to be sent with a message.

    ``id`` is opaque to the client; the local path stays inside the daemon."""

    id: str
    filename: str
    mime: str
    size: int


def attachment_note(attachments: Sequence[Attachment]) -> str:
    """A short stand-in text for a message that carries files and no text, so
    the persisted user turn is not blank — an agent's request cannot hold an
    empty text block. Shared by a channel's uncaptioned photo and the web
    composer's attachment-only send."""
    names = ", ".join(a.filename for a in attachments)
    kind = "image" if all(a.is_image for a in attachments) else "file"
    plural = "s" if len(attachments) != 1 else ""
    return f"(sent {len(attachments)} {kind}{plural}: {names})"


def clean_upload_filename(name: str | None) -> str:
    """The display name an upload keeps: its last path segment, control
    characters dropped, clipped to 255 characters; ``"attachment"`` when
    nothing is left. It is shown on the page and told to the agent, never used
    to build a path."""
    base = re.split(r"[\\/]", name or "")[-1]
    base = "".join(ch for ch in base if ch.isprintable()).strip()
    return base[:255] or "attachment"


def is_upload_id(value: str) -> bool:
    """Whether ``value`` has the shape of an upload id (never a path)."""
    return bool(_UPLOAD_ID.fullmatch(value))


def _looks_like_text(data: bytes) -> bool:
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


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
    once encoded. Channel media and web uploads both pass through here."""
    if base64_size(len(data)) > INLINE_IMAGE_MAX_BYTES:
        return None
    return sniff_image_mime(data)


def upload_mime(filename: str, declared: str | None, data: bytes) -> str | None:
    """The mime an upload is stored under, or ``None`` when its type is refused.

    Accepted: images, audio and documents — by the declared type first, then by
    the file's extension — and anything whose bytes are UTF-8 text (source code,
    Markdown, JSON, logs), whatever the browser called it. An image is stored
    under the type its bytes prove, so a JPEG named ``.png`` is ``image/jpeg``;
    one whose bytes are no recognised format is stored as a generic file
    (:data:`GENERIC_MIME`), never as an image. Refused: everything else (video,
    archives, executables), which no agent can use from a turn.
    """
    claimed = (declared or "").split(";", 1)[0].strip().lower()
    mime = claimed
    if not (mime.startswith(("image/", "audio/")) or mime in DOCUMENT_MIMES):
        mime = _EXTENSION_MIMES.get(pathlib.PurePath(filename).suffix.lower(), "")
    if mime.startswith("image/"):
        return sniff_image_mime(data) or GENERIC_MIME
    if mime:
        return mime
    if _looks_like_text(data):
        return claimed if claimed.startswith("text/") else "text/plain"
    return None


__all__ = [
    "DOCUMENT_EXTENSIONS",
    "DOCUMENT_MIMES",
    "GENERIC_MIME",
    "INLINE_IMAGE_MAX_BYTES",
    "MAX_ATTACHMENTS_PER_MESSAGE",
    "MAX_ATTACHMENT_BYTES",
    "Attachment",
    "UploadedAttachment",
    "attachment_note",
    "base64_size",
    "clean_upload_filename",
    "inline_image_mime",
    "is_upload_id",
    "sniff_image_mime",
    "upload_mime",
]
