"""Turning an uploaded document into a source for a collection.

An upload is one of the entrances new knowledge arrives by — the Knowledge page's upload
button and a channel attachment (see "Keep every upload as a source with its original"
and "Ingest documents sent to a channel"). The document is converted to Markdown and
**submitted as material**: it goes through :meth:`KnowledgeService.submit`, which keeps
it as a source under ``sources/`` on the spot (see "Promote submitted material at
once"), with the original file beside it unless the Markdown already was the file.

What this module owns that ``submit`` does not need to think about: **the
description is optional input, never optional output.** The catalogue the
delivered skill carries is how an agent learns a document exists (see "Merge the
manual and the catalogue in the skill body"), so every upload gets a description,
drawn from its own opening prose (see "Fill frontmatter on converted material").
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.knowledge.converter import Conversion, EmptyConversion
from coffer.domain.knowledge.entry import ACTOR_USER
from coffer.domain.knowledge.errors import UploadTooLarge
from coffer.infrastructure.knowledge.naming import opening_prose


@runtime_checkable
class ConverterRegistry(Protocol):
    """Structural port onto ``infrastructure.knowledge.converters.registry``.

    Import-linter's engine-confinement contract keeps ``markitdown`` reachable
    only from ``infrastructure.chat`` and ``infrastructure.knowledge`` — not
    from ``application``, even transitively through the real registry class.
    A ``Protocol`` lets the composition root hand this service the real
    ``ConverterRegistry`` (which satisfies this shape structurally, no
    inheritance needed) without this module ever importing it.
    """

    async def convert(self, data: bytes, filename: str) -> Conversion: ...


#: One upload at a time, bounded so a single call cannot exhaust memory or disk (see
#: "Bound uploads and leave nothing behind on failure"). 20 MB matches the tightest
#: existing bound in this codebase for a document passed hand-to-hand rather than
#: streamed — Telegram's own bot-API download cap
#: (``infrastructure/channel/telegram_media.py``) — which keeps the two entrances
#: "Ingest documents sent to a channel" unifies (the Knowledge page and a channel
#: attachment) under one honest ceiling rather than the page silently accepting what a
#: phone never could.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

#: The converter that reads a file as it stands: its Markdown is the original.
PASSTHROUGH = "passthrough"


@dataclass(frozen=True)
class IngestedDocument:
    """What one successful ingest produced.

    ``path`` is the source the upload became.
    """

    path: str
    title: str
    description: str
    #: Name of the converter that produced the Markdown (``Conversion.converter``).
    converter: str


class IngestService:
    """Converts and writes one uploaded document at a time."""

    def __init__(
        self,
        *,
        knowledge: KnowledgeService,
        registry: ConverterRegistry,
    ) -> None:
        self._knowledge = knowledge
        self._registry = registry

    async def ingest(
        self,
        *,
        collection: str,
        filename: str,
        data: bytes,
        actor: str,
    ) -> IngestedDocument:
        """Convert ``data`` (named ``filename``) and submit it as material.

        Raises ``UploadTooLarge`` over the size ceiling, ``UnsupportedDocument``
        (``domain.knowledge.converter``) for a type no converter handles,
        ``EmptyConversion`` when a converter ran and produced no text, and
        whatever ``KnowledgeService.submit`` raises for an unknown or
        otherwise invalid target — in every one of those cases nothing is
        written, converted or kept (see "Bound uploads and leave nothing
        behind on failure").
        """
        if len(data) > MAX_UPLOAD_BYTES:
            raise UploadTooLarge(len(data), MAX_UPLOAD_BYTES)

        # The same check `submit` itself makes, run here and up front so
        # a name that is not a collection is refused without first paying for
        # the conversion.
        await self._knowledge.require_collection(collection)

        conversion = await self._registry.convert(data, filename)
        # "Bound uploads and leave nothing behind on failure": a converter that succeeds
        # but extracts nothing (an image-only PDF is the real case) must not be stored
        # as a titled file with an empty body. Checked here rather than in each
        # converter so every format is covered by one rule.
        if not conversion.markdown.strip():
            raise EmptyConversion(pathlib.Path(filename).suffix.lstrip(".").lower())
        description = _fallback_description(conversion.markdown, title=conversion.title)

        # The Markdown is the original when it was read as it stands; anything
        # converted keeps its own file beside the source ("Keep every upload
        # as a source with its original").
        original = None if conversion.converter == PASSTHROUGH else (filename, data)
        submitted = await self._knowledge.submit(
            collection=collection,
            title=conversion.title,
            description=description,
            body=conversion.markdown,
            actor_kind=ACTOR_USER,
            actor=actor,
            original=original,
        )
        return IngestedDocument(
            path=submitted.document.path,
            title=conversion.title,
            description=description,
            converter=conversion.converter,
        )


def _fallback_description(markdown: str, *, title: str) -> str:
    """The document's own opening prose, or its title — never empty ("Carry
    title, description and actor in frontmatter" makes the description required)."""
    return opening_prose(markdown, fallback=title)


__all__ = [
    "MAX_UPLOAD_BYTES",
    "IngestService",
    "IngestedDocument",
]
