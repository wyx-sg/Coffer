"""The document→Markdown conversion contract (spec knowledge FR-033..FR-035).

Pure: this module describes what the knowledge layer needs from a converter,
so ``domain/`` never imports ``markitdown`` or any other conversion engine —
those live in ``infrastructure/knowledge/converters/`` and are dispatched by
the registry there. This module only turns bytes + a filename into Markdown
text; writing the resulting file, filling in its description, and keeping the
``.raw/`` original are a different layer's job.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Conversion:
    """The result of turning one uploaded document into Markdown."""

    markdown: str
    #: The document's own title (its first Markdown H1) when it has one, else
    #: the uploaded file's own name (FR-034).
    title: str
    #: Which converter produced this. Reported on the successful upload
    #: response (``IngestedDocumentOut.converter``) so the caller knows which
    #: converter's output it is looking at — a conversion that FAILED raises
    #: instead, and the engine-level failure names its own engine
    #: (``EngineUnavailable``).
    converter: str


class UnsupportedDocument(Exception):  # noqa: N818 - carries the rejected type, not an "...Error"
    """No converter handles this file type; nothing was written (FR-033)."""

    def __init__(self, doc_type: str) -> None:
        self.doc_type = doc_type
        super().__init__(f"unsupported document type: {doc_type!r}")


class EmptyConversion(Exception):  # noqa: N818 - carries the rejected type, not an "...Error"
    """A converter ran and produced nothing; nothing was written (FR-037).

    The case that matters is an image-only PDF: MarkItDown extracts no text
    from it, returns ``""``, and reports no error — it did its job, the
    document simply has no text layer. Stored, that is a knowledge file with a
    title and an empty body, which FR-037's "never half-converted" forbids and
    which is worse than a refusal: search will never find it and nothing says
    why.

    A sibling of :class:`UnsupportedDocument` and, like it, deliberately NOT a
    ``CofferError``: both are refusals of one upload that the route turns into
    the family's single ``INGEST_REJECTED`` code, distinguished by
    ``details.reason``.
    """

    def __init__(self, doc_type: str) -> None:
        self.doc_type = doc_type
        super().__init__(f"converter produced no text for a {doc_type!r} document")


@runtime_checkable
class Converter(Protocol):
    """Converts one document's bytes to Markdown for a family of formats."""

    def can_handle(self, fmt: str) -> bool:
        """Whether this converter handles the given lower-cased extension."""
        ...

    async def convert(self, data: bytes, filename: str) -> Conversion:
        """Convert ``data`` — the file named ``filename`` — to Markdown."""
        ...


def derive_title(markdown: str, filename: str) -> str:
    """The document's own title, else the uploaded file's own name (FR-034).

    Only the first non-blank line is treated as a heading candidate: an H1
    appearing lower in the document introduces a section, not the document.
    """
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# "):
            return stripped[2:].strip()
        break
    return pathlib.Path(filename).stem
