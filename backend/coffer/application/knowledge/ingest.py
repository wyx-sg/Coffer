"""Turning an uploaded document into new knowledge for a collection.

An upload is one of the entrances new knowledge arrives by — the Knowledge page's upload
button and a channel attachment (see "Convert uploads into material without keeping
them" and "Ingest documents sent to a channel"). The document is converted to Markdown
and **submitted as material**, exactly as an agent's ``coffer__write`` is: it goes
through :meth:`KnowledgeService.submit`, so a curation pass folds what is new in it into
the collection's documents, and with no internal model it becomes a document of its own
(see "Promote material directly when no model is configured"). Nothing else of the
upload is kept — not the original bytes, not the extracted text as a file of its own:
what the collection holds is the knowledge, merged, and the document it arrived in was
only its carrier.

What this module owns that ``submit`` does not need to think about:

* **The description is optional input, never optional output.** The catalogue the
  delivered skill carries is how an agent learns a document exists (see "Merge the
  manual and the catalogue in the skill body"), so material that arrives with no
  internal connection configured — or whose connection fails or stalls — still gets a
  description, drawn from its own opening prose (see "Fill frontmatter on converted
  material").

Following ``curate.py``'s shape: the internal connection is reached through
``ModelSelectorPort`` + ``LlmCompletionPort``, both optional, and their
absence degrades cleanly rather than failing the ingest.
"""

from __future__ import annotations

import asyncio
import contextlib
import pathlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from coffer.application.engine_ports import LlmCompletionPort, ModelSelectorPort
from coffer.application.engine_timeout import (
    DEFAULT_MODEL_TIMEOUT_S,
    TimeoutReader,
    resolve_timeout,
)
from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.knowledge.converter import Conversion, EmptyConversion
from coffer.domain.knowledge.entry import ACTOR_USER
from coffer.domain.knowledge.errors import UploadTooLarge


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

#: A one-line description is a small job (spec knowledge "Fill frontmatter on converted
#: material"), not an agentic loop; bounded generously so a slow provider cannot hang an
#: upload, but nowhere near indefinite. Superseded by the operator's own bound (spec
#: internal-engine "Run every internal model call under the bound"). The twenty seconds
#: this used to carry was the tightest bound anywhere in Coffer, and a description that
#: times out costs the catalogue its one line about a document — the line every later
#: search reads it by.
_DESCRIPTION_TIMEOUT_SECONDS = DEFAULT_MODEL_TIMEOUT_S

_DESCRIPTION_SYSTEM = (
    "You write the one-line description for a knowledge-base catalogue entry. "
    "Reply with exactly one plain sentence describing what the document is "
    "about, under 30 words, no preamble, no quotes, no markdown."
)

#: How much of a converted document to hand the model — enough to describe
#: it, small enough to keep the call cheap regardless of the source file size.
_DESCRIPTION_SOURCE_CHARS = 4000

#: Length of the opening-prose fallback description, for the same reason.
_FALLBACK_DESCRIPTION_CHARS = 240


@dataclass(frozen=True)
class IngestedDocument:
    """What one successful ingest produced.

    ``path`` is the document the upload became when it was promoted on the spot
    (no model to merge it); ``None`` when it waits in the inbox for a pass,
    which is what ``pending`` says.
    """

    path: str | None
    title: str
    description: str
    #: Name of the converter that produced the Markdown (``Conversion.converter``).
    converter: str
    pending: bool


class IngestService:
    """Converts, describes, and writes one uploaded document at a time."""

    def __init__(
        self,
        *,
        knowledge: KnowledgeService,
        registry: ConverterRegistry,
        models: ModelSelectorPort | None = None,
        completion: LlmCompletionPort | None = None,
        credential_resolver: Callable[[str], str] | None = None,
        read_timeout: TimeoutReader | None = None,
    ) -> None:
        self._knowledge = knowledge
        self._registry = registry
        self._models = models
        self._completion = completion
        self._credential_resolver = credential_resolver
        self._read_timeout = read_timeout

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
        await self._knowledge.require_enabled(collection)

        conversion = await self._registry.convert(data, filename)
        # "Bound uploads and leave nothing behind on failure": a converter that succeeds
        # but extracts nothing (an image-only PDF is the real case) must not be stored
        # as a titled file with an empty body. Checked here rather than in each
        # converter so every format is covered by one rule, and BEFORE the describe call
        # so a refusal costs no model tokens either.
        if not conversion.markdown.strip():
            raise EmptyConversion(pathlib.Path(filename).suffix.lstrip(".").lower())
        description = await self._describe(conversion.markdown, title=conversion.title)

        submitted = await self._knowledge.submit(
            collection=collection,
            title=conversion.title,
            description=description,
            body=conversion.markdown,
            actor_kind=ACTOR_USER,
            actor=actor,
        )
        return IngestedDocument(
            path=submitted.document.path if submitted.document else None,
            title=conversion.title,
            description=description,
            converter=conversion.converter,
            pending=submitted.pending is not None,
        )

    async def _describe(self, markdown: str, *, title: str) -> str:
        """A one-line description, from the internal connection when one is
        configured and reachable, else the document's own opening prose."""
        if self._models is not None and self._completion is not None:
            model = await self._models.get_default()
            if model is not None and self._credential_resolver is not None:
                with contextlib.suppress(Exception):
                    timeout = await resolve_timeout(self._read_timeout)
                    described = await asyncio.wait_for(
                        self._completion.complete(
                            system=_DESCRIPTION_SYSTEM,
                            user=markdown[:_DESCRIPTION_SOURCE_CHARS],
                            model=model,
                            credential_resolver=self._credential_resolver,
                            timeout=timeout,
                        ),
                        timeout=timeout,
                    )
                    cleaned = " ".join(described.split())
                    if cleaned:
                        return cleaned
        return _fallback_description(markdown, title=title)


def _fallback_description(markdown: str, *, title: str) -> str:
    """The document's own opening prose — first paragraph, headings skipped.

    Never empty ("Carry title, description and actor in frontmatter" makes the
    description required): a document with no
    prose of its own — a bare table, a blank file — falls back to its title,
    which ``derive_title`` guarantees is never empty either.
    """
    paragraph: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if not stripped:
            if paragraph:
                break
            continue
        paragraph.append(stripped)
    text = " ".join(paragraph).strip()
    return text[:_FALLBACK_DESCRIPTION_CHARS] if text else title


__all__ = [
    "MAX_UPLOAD_BYTES",
    "IngestService",
    "IngestedDocument",
]
