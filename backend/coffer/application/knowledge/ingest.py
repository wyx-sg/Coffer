"""Turning an uploaded document into ordinary files in the sources lane.

Dropping a Markdown file into ``sources/`` is already a complete way to add
knowledge (FR-015); this module is the *additional* entrance, for the cases
where the filesystem is out of reach — the Knowledge page's upload button and
a channel attachment (FR-018). Nothing here changes what a source is: the
output of :meth:`IngestService.ingest` must be indistinguishable from a file a
person put there by hand, so it goes through
:meth:`KnowledgeService.write_source` rather than touching the filesystem
itself — the same audit event, the same frontmatter, the same scope
enforcement as any other write.

Two things this module owns that ``write_source`` does not need to think about:

* **The original bytes are worth keeping, and worth seeing.** A bad conversion
  has to be redoable from what the user actually sent. The original used to go
  into a hidden ``.raw/`` directory, and the only thing hiding it bought was
  keeping it out of retrieval — an original is bytes, not prose, and a ranked
  index that surfaced it would be answering with noise. Coffer exposes no
  retrieval surface any more (FR-033): an agent reads the files it is given
  paths to, and nothing sweeps the lane. So the original is now an ordinary,
  visible file in ``sources/`` beside the text extracted from it (FR-016),
  which is also what a person scrolling their own lane should see.
* **The description is optional input, never optional output.** The catalogue
  the delivered skill carries is how an agent learns a document exists
  (FR-037), so a document that arrives with no internal connection configured
  — or whose connection fails or stalls — still gets a description, drawn from
  its own opening prose (FR-017).

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
from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.knowledge.converter import Conversion, EmptyConversion
from coffer.domain.knowledge.entry import ACTOR_USER
from coffer.domain.knowledge.errors import UploadTooLarge
from coffer.infrastructure.knowledge import fs


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


#: One upload at a time, bounded so a single call cannot exhaust memory or
#: disk (FR-019). 20 MB matches the tightest existing bound in this codebase
#: for a document passed hand-to-hand rather than streamed — Telegram's own
#: bot-API download cap (``infrastructure/channel/telegram_media.py``) — which
#: keeps the two entrances FR-018 unifies (the Knowledge page and a channel
#: attachment) under one honest ceiling rather than the page silently
#: accepting what a phone never could.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

#: A one-line description is a small job (spec knowledge FR-017), not an
#: agentic loop; bounded generously so a slow provider cannot hang an upload,
#: but nowhere near indefinite.
_DESCRIPTION_TIMEOUT_SECONDS = 20.0

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
    """What one successful ingest produced: two files in the same lane."""

    #: Knowledge-root-relative path of the Markdown ``write_source`` created.
    path: str
    title: str
    description: str
    #: Name of the converter that produced the Markdown (``Conversion.converter``).
    converter: str
    #: Knowledge-root-relative path of the original, sitting in ``sources/``
    #: beside the Markdown extracted from it (FR-016). Relative like ``path``
    #: because it is now an ordinary file in the lane a person browses, not a
    #: hidden location only an absolute path could name. Equal to ``path`` when
    #: the upload was already Markdown: the file that landed *is* the original,
    #: and a second copy of it would be curated as a second source.
    original_path: str


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
    ) -> None:
        self._knowledge = knowledge
        self._registry = registry
        self._models = models
        self._completion = completion
        self._credential_resolver = credential_resolver

    async def ingest(
        self,
        *,
        collection: str,
        filename: str,
        data: bytes,
        folder: str | None = None,
        actor: str,
        agent: str | None = None,
    ) -> IngestedDocument:
        """Convert ``data`` (named ``filename``) into a source file.

        ``folder`` is an optional subdirectory *inside* the collection's
        ``sources/``; the lane segment itself is never spelled by a caller
        (FR-013), so no entrance can aim an upload at ``topics/``.

        Raises ``UploadTooLarge`` over the size ceiling, ``UnsupportedDocument``
        (``domain.knowledge.converter``) for a type no converter handles,
        ``EmptyConversion`` when a converter ran and produced no text, and
        whatever ``KnowledgeService.write_source`` raises for an unauthorized
        or otherwise invalid target — in every one of those cases nothing is
        written, converted or kept (FR-019).
        """
        if len(data) > MAX_UPLOAD_BYTES:
            raise UploadTooLarge(len(data), MAX_UPLOAD_BYTES)

        # The same enforcement point `write_source` itself uses
        # (FR-010/FR-012): calling it here, before conversion, refuses an
        # unauthorized upload without first paying for the conversion.
        await self._knowledge.require_visible(collection, agent)

        conversion = await self._registry.convert(data, filename)
        # FR-019: a converter that succeeds but extracts nothing (an image-only
        # PDF is the real case) must not be stored as a titled file with an
        # empty body. Checked here rather than in each converter so every
        # format is covered by one rule, and BEFORE the describe call so a
        # refusal costs no model tokens either.
        if not conversion.markdown.strip():
            raise EmptyConversion(pathlib.Path(filename).suffix.lstrip(".").lower())
        description = await self._describe(conversion.markdown, title=conversion.title)

        written = await self._knowledge.write_source(
            title=conversion.title,
            description=description,
            body=conversion.markdown,
            collection=collection,
            folder=folder or None,
            actor_kind=ACTOR_USER,
            actor=actor,
            agent=agent,
        )

        # A Markdown upload converts by passthrough, so the "original" would be
        # the bytes already sitting in the file just written — two copies of one
        # document in the lane a person browses, and two curation passes over
        # the same facts. The live vault's 50 documents were all passthrough, so
        # this is the common case rather than a corner one.
        if _is_the_same_bytes(conversion.markdown, data):
            return IngestedDocument(
                path=written.path,
                title=written.title,
                description=written.description,
                converter=conversion.converter,
                original_path=written.path,
            )

        try:
            original_path = fs.write_original(collection, filename, data)
        except Exception:
            # Half of FR-019's all-or-nothing: the Markdown must not outlive
            # the original it was supposed to stand next to.
            with contextlib.suppress(Exception):
                fs.delete_file(written.path)
            raise

        return IngestedDocument(
            path=written.path,
            title=written.title,
            description=written.description,
            converter=conversion.converter,
            original_path=original_path,
        )

    async def _describe(self, markdown: str, *, title: str) -> str:
        """A one-line description, from the internal connection when one is
        configured and reachable, else the document's own opening prose."""
        if self._models is not None and self._completion is not None:
            model = await self._models.get_default()
            if model is not None and self._credential_resolver is not None:
                with contextlib.suppress(Exception):
                    described = await asyncio.wait_for(
                        self._completion.complete(
                            system=_DESCRIPTION_SYSTEM,
                            user=markdown[:_DESCRIPTION_SOURCE_CHARS],
                            model=model,
                            credential_resolver=self._credential_resolver,
                        ),
                        timeout=_DESCRIPTION_TIMEOUT_SECONDS,
                    )
                    cleaned = " ".join(described.split())
                    if cleaned:
                        return cleaned
        return _fallback_description(markdown, title=title)


def _is_the_same_bytes(markdown: str, data: bytes) -> bool:
    """Whether the conversion is just the upload, decoded.

    Compared on content rather than on the converter's name: what matters is
    that keeping the original would store the same text twice, and a converter
    that happens to be a no-op for some input is the same situation as one
    that is a no-op by design.
    """
    try:
        return markdown.strip() == data.decode("utf-8").strip()
    except UnicodeDecodeError:
        return False


def _fallback_description(markdown: str, *, title: str) -> str:
    """The document's own opening prose — first paragraph, headings skipped.

    Never empty (FR-003 makes the description required): a document with no
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
