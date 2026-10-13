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
from typing import Protocol, runtime_checkable

#: How a converter's Markdown names a file it keeps beside the source
#: (:class:`ConvertedFile`); the ingest points each such link at where the file
#: is kept.
ASSET_LINK_PREFIX = "coffer-asset:"


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
    """A file kept beside the source as it came: a picture, a diagram source
    or the original Storage Format of an imported page (design §5).

    ``name`` is a safe file name; the Markdown links it as
    ``coffer-asset:<name>``.
    """

    name: str
    data: bytes


@dataclass(frozen=True)
class ConversionIssue:
    """Something an import could not keep, and why (design §5).

    ``kind`` is one of ``missing_attachment``, ``external_embed``,
    ``external_image``, ``unsupported_macro`` or ``not_rendered``.
    """

    kind: str
    name: str
    reason: str


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
    #: Files kept as they came, linked from the Markdown as ``coffer-asset:<name>``.
    files: tuple[ConvertedFile, ...] = ()
    #: What the conversion could not keep, each with its reason.
    issues: tuple[ConversionIssue, ...] = ()
    #: Extra frontmatter keys the source carries (never ``title``,
    #: ``description``, ``actor``, ``created_at`` or ``updated_at``).
    metadata: Mapping[str, object] = field(default_factory=dict, hash=False)
    #: The folder the kept files would like; ``""`` lets the ingest decide.
    asset_folder: str = ""
    #: Whether the uploaded file is kept as the original; ``None`` keeps the
    #: existing rule (every converter but passthrough).
    keeps_original: bool | None = None


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
