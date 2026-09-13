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
    #: Which converter produced this — carried so a failure message downstream
    #: can say what ran, without re-deriving it from the file extension.
    converter: str


class UnsupportedDocument(Exception):  # noqa: N818 - carries the rejected type, not an "...Error"
    """No converter handles this file type; nothing was written (FR-033)."""

    def __init__(self, doc_type: str) -> None:
        self.doc_type = doc_type
        super().__init__(f"unsupported document type: {doc_type!r}")


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
