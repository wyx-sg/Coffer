"""The document→Markdown conversion contract (spec knowledge).

Pure: this module describes what the knowledge layer needs from a converter,
so ``domain/`` never imports ``markitdown`` or any other conversion engine —
those live in ``infrastructure/knowledge/converters/`` and are dispatched by
the registry there. This module only turns bytes + a filename into Markdown
text; submitting it as material and filling in its description are a
different layer's job.
"""

from __future__ import annotations

import pathlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ConvertedImage:
    """One picture taken out of an uploaded document, kept beside its source
    (ADR knowledge-sources-keep-their-images-and-originals-stay-on-this-mac).

    ``name`` is how the Markdown refers to it (``![…](name)``) until the
    source is written and the link is pointed at where it is kept.
    """

    name: str
    data: bytes


@dataclass(frozen=True)
class ConvertedFile:
    """Any other file a conversion keeps beside its source, under the
    folder the conversion names (:attr:`Conversion.asset_folder`): an
    attachment the document refers to, a diagram's source, the raw form the
    readable Markdown was made from. The Markdown already links it by
    ``../assets/<folder>/<name>``."""

    name: str
    data: bytes


#: How each part of an import ended (``ImportItem.status``).
ITEM_KEPT = "kept"
ITEM_CONVERTED = "converted"
ITEM_SOURCE_KEPT = "source_kept"
ITEM_DROPPED = "dropped"
ITEM_MISSING = "missing"
ITEM_UNSUPPORTED = "unsupported"
ITEM_SKIPPED = "skipped"


@dataclass(frozen=True)
class ImportItem:
    """One attachment, embed or macro of an imported document, and how it
    ended: ``kept`` beside the source, ``converted`` into the Markdown,
    ``source_kept`` (a diagram's source kept, no picture of it), ``dropped``
    (generated content such as a table of contents), ``missing`` (it could not
    be had: not downloaded, behind someone else's permission), ``unsupported``
    (Coffer does not read it) or ``skipped`` (not referenced by the document)."""

    name: str
    status: str
    reason: str = ""
    #: Where it is kept, relative to the source, when it is.
    path: str = ""


#: ``ImportReport.body``: every part of the text was read, or some was not.
BODY_CONVERTED = "converted"
BODY_PARTIAL = "partial"


@dataclass(frozen=True)
class ImportReport:
    """What an import of a structured document did, part by part, so a partial
    import is never reported as a plain success (spec knowledge "Import a
    Confluence page as a readable source with its attachments")."""

    body: str = BODY_CONVERTED
    attachments: tuple[ImportItem, ...] = ()
    macros: tuple[ImportItem, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        """Whether nothing was left behind: the body converted whole and no
        attachment or macro is missing or unsupported."""
        bad = {ITEM_MISSING, ITEM_UNSUPPORTED}
        return self.body == BODY_CONVERTED and not any(
            item.status in bad for item in (*self.attachments, *self.macros)
        )


@dataclass(frozen=True)
class Conversion:
    """The result of turning one uploaded document into Markdown."""

    markdown: str
    #: The document's own title (its first Markdown H1) when it has one, else
    #: the uploaded file's own name ("Fill frontmatter on converted material").
    title: str
    #: Which converter produced this. Reported on the successful upload
    #: response (``IngestedDocumentOut.converter``) so the caller knows which
    #: converter's output it is looking at — a conversion that FAILED raises
    #: instead, and the engine-level failure names its own engine
    #: (``EngineUnavailable``).
    converter: str
    #: The pictures the Markdown refers to by name, in order of appearance.
    images: tuple[ConvertedImage, ...] = ()
    #: Frontmatter the document carried or the converter read off it — its
    #: own title, where it came from, its version — kept on the source. Never
    #: the keys Coffer writes itself (``actor``, the timestamps).
    metadata: Mapping[str, Any] = field(default_factory=dict)
    #: Other files kept beside the source, in :attr:`asset_folder`.
    files: tuple[ConvertedFile, ...] = ()
    #: The folder under ``assets/`` the conversion's files go in, when the
    #: converter names it (a Confluence page by its id and version); ``None``
    #: lets the upload name it.
    asset_folder: str | None = None
    #: Part by part, what a structured import did; ``None`` for a plain file.
    report: ImportReport | None = None


class UnsupportedDocument(Exception):  # noqa: N818 - carries the rejected type, not an "...Error"
    """No converter handles this file type; nothing was written.

    Spec knowledge "Keep every upload as a Markdown source".
    """

    def __init__(self, doc_type: str) -> None:
        self.doc_type = doc_type
        super().__init__(f"unsupported document type: {doc_type!r}")


class EmptyConversion(Exception):  # noqa: N818 - carries the rejected type, not an "...Error"
    """A converter ran and produced nothing; nothing was written.

    Spec knowledge "Bound uploads and leave nothing behind on failure".

    The case that matters is an image-only PDF: MarkItDown extracts no text
    from it, returns ``""``, and reports no error — it did its job, the
    document simply has no text layer. Stored, that is a knowledge file with a
    title and an empty body, which that requirement's "no inbox item, no
    document" forbids and which is worse than a refusal: search will never
    find it and nothing says why.

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
    """The document's own title, else the uploaded file's own name.

    Spec knowledge "Fill frontmatter on converted material".

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
