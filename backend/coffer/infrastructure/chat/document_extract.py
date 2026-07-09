"""Document text-extraction seam for inbound documents (spec 009 FR-030).

An inbound document (PDF, docx, pptx, xlsx, …) should reach the agent as
**extracted text folded into the turn**, not as a vision input or an opaque
binary path. A path-native agent (Codex/Hermes/OpenCode/Cursor) otherwise only
gets a "file saved at /path" note and cannot parse a binary PDF; a vision agent
would waste the document as an image. So the adapter extracts the document to
text before building the turn — mirroring the audio transcription seam.

The engine is injected behind :class:`DocumentExtractor` so turns are testable
with a fake, and the real one is a lazily-imported optional dependency
(``markitdown``) — absent (or on any extraction failure), extraction degrades to
handing over the document as a file attachment (the current path-note behaviour),
never wedging the turn. Images stay vision-inlined and audio stays transcribed;
only documents go through here.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import pathlib
from collections.abc import Sequence
from typing import Protocol

from coffer.domain.chat.attachment import Attachment

_logger = logging.getLogger(__name__)

#: Document mime types markitdown can convert to text. Images, audio, and plain
#: text/code are deliberately excluded — an agent reads a path to those fine, and
#: an image belongs on the vision path.
_DOCUMENT_MIMES = frozenset(
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

#: Extension fallback for when a channel hands over a generic mime (e.g.
#: ``application/octet-stream``) but a document filename.
_DOCUMENT_EXTENSIONS = frozenset(
    {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".rtf", ".epub", ".csv"}
)


def _is_document(att: Attachment) -> bool:
    """True when the attachment is a document to text-extract (never an image or
    audio; matched by mime, else by filename extension)."""
    if att.is_image or att.mime.startswith("audio/"):
        return False
    if att.mime in _DOCUMENT_MIMES:
        return True
    ext = pathlib.Path(att.filename or att.path).suffix.lower()
    return ext in _DOCUMENT_EXTENSIONS


class DocumentExtractor(Protocol):
    """Turn a document file into text. Returns "" when it cannot (never raises to
    the caller — the adapter then falls back to handing over the file path)."""

    async def extract(self, path: str) -> str: ...


class MarkItDownExtractor:
    """``markitdown`` (Microsoft's converter, pdf/docx/pptx/xls/xlsx/… → markdown),
    imported lazily so the dependency stays optional and tests need not install it.
    Runs the blocking convert off the event loop."""

    async def extract(self, path: str) -> str:
        try:
            from markitdown import MarkItDown
        except ImportError:
            _logger.info("document_extract.markitdown_absent — document not extracted")
            return ""
        try:
            result = await asyncio.to_thread(MarkItDown().convert, path)
        except Exception:
            _logger.warning("document_extract.failed", extra={"path": path}, exc_info=True)
            return ""
        return str(getattr(result, "text_content", "") or "").strip()


def default_document_extractor() -> DocumentExtractor | None:
    """The markitdown-backed extractor when the optional dependency is importable,
    else ``None`` — the adapter then hands over the document file untouched."""
    if importlib.util.find_spec("markitdown") is not None:
        return MarkItDownExtractor()
    return None


async def extract_document_attachments(
    attachments: Sequence[Attachment], extractor: DocumentExtractor | None
) -> tuple[list[Attachment], list[tuple[str, str]]]:
    """Split ``attachments`` into (the non-document ones to keep, ``(filename,
    text)`` extracts of the document ones). With no extractor — or when extraction
    yields nothing — a document is kept as an attachment so the agent still
    receives the file path (degrades, never wedges the turn)."""
    if extractor is None:
        return list(attachments), []
    kept: list[Attachment] = []
    extracts: list[tuple[str, str]] = []
    for att in attachments:
        if _is_document(att):
            text = (await extractor.extract(att.path)).strip()
            if text:
                extracts.append((att.filename, text))
                continue
        kept.append(att)
    return kept, extracts


def prompt_with_document_text(prompt: str, extracts: Sequence[tuple[str, str]]) -> str:
    """Fold extracted document text into the turn's prompt, each labelled with its
    filename so the agent knows where it came from."""
    if not extracts:
        return prompt
    docs = "\n\n".join(f"[Document: {name}]\n{text}" for name, text in extracts)
    return f"{prompt}\n\n{docs}".strip() if prompt else docs


__all__ = [
    "DocumentExtractor",
    "MarkItDownExtractor",
    "default_document_extractor",
    "extract_document_attachments",
    "prompt_with_document_text",
]
