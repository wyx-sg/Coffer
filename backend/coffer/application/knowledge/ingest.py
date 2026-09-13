"""Turning an uploaded document into an ordinary knowledge file.

Placing a Markdown file in the directory is already a complete way to add
knowledge (FR-032); this module is the *additional* entrance for the cases
where the filesystem is out of reach — the Knowledge page's upload button and
a channel attachment (FR-036). Nothing here changes what a knowledge file is:
the output of :meth:`IngestService.ingest` must be indistinguishable from a
file a human typed by hand, so it goes through :meth:`KnowledgeService.write`
rather than touching the filesystem itself — the same audit event, the same
frontmatter, the same scope enforcement as any other write.

Two things this module owns that ``write`` does not need to think about:

* **The original bytes are worth keeping.** A bad conversion should be
  redoable from what the user actually sent, so the upload is copied to
  ``.raw/`` (``paths.raw_path``) once the converted file's name is known.
* **The description is optional input, never optional output.** With no
  ranked index the catalogue entry is the whole retrieval surface (FR-003), so
  a document that arrives with no internal connection configured — or whose
  connection fails or stalls — still gets a description, drawn from its own
  opening prose (spec knowledge FR-034).

Following ``tidy.py``'s shape: the internal connection is reached through
``ModelSelectorPort`` + ``LlmCompletionPort``, both optional, and their
absence degrades cleanly rather than failing the ingest.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from coffer.application.engine_ports import LlmCompletionPort, ModelSelectorPort
from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.knowledge.converter import Conversion
from coffer.domain.knowledge.entry import ACTOR_USER
from coffer.domain.knowledge.errors import UploadTooLarge
from coffer.infrastructure.knowledge import fs, paths


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
#: disk (FR-037). 20 MB matches the tightest existing bound in this codebase
#: for a document passed hand-to-hand rather than streamed — Telegram's own
#: bot-API download cap (``infrastructure/channel/telegram_media.py``) — which
#: keeps the two entrances FR-036 unifies (the Knowledge page and a channel
#: attachment) under one honest ceiling rather than the page silently
#: accepting what a phone never could.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

#: A one-line description is a small job (spec knowledge FR-034), not an
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
    """What one successful ingest produced."""

    #: Knowledge-root-relative path of the Markdown file ``write`` created.
    path: str
    title: str
    description: str
    #: Name of the converter that produced the Markdown (``Conversion.converter``).
    converter: str
    #: Absolute path of the kept original, under ``.raw/``.
    raw_path: str


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
        directory: str | None = None,
        actor: str,
        agent: str | None = None,
    ) -> IngestedDocument:
        """Convert ``data`` (named ``filename``) into a knowledge file.

        Raises ``UploadTooLarge`` over the size ceiling, ``UnsupportedDocument``
        (``domain.knowledge.converter``) for a type no converter handles, and
        whatever ``KnowledgeService.write`` raises for an unauthorized or
        otherwise invalid target — in every one of those cases nothing is
        written, converted or kept (FR-037).
        """
        if len(data) > MAX_UPLOAD_BYTES:
            raise UploadTooLarge(len(data), MAX_UPLOAD_BYTES)

        target_directory = f"{collection}/{directory.strip('/')}" if directory else collection
        # The same enforcement point `write` itself uses (FR-012/FR-014):
        # calling it here, before conversion, refuses an unauthorized upload
        # without first paying for the conversion.
        await self._knowledge.require_visible(target_directory, agent)

        conversion = await self._registry.convert(data, filename)
        description = await self._describe(conversion.markdown, title=conversion.title)

        written = await self._knowledge.write(
            title=conversion.title,
            description=description,
            body=conversion.markdown,
            directory=target_directory,
            actor_kind=ACTOR_USER,
            actor=actor,
            agent=agent,
        )

        raw_target = paths.raw_path(written.path, filename)
        try:
            raw_target.parent.mkdir(parents=True, exist_ok=True)
            raw_target.write_bytes(data)
        except Exception:
            # Half of FR-037's all-or-nothing: the Markdown file must not
            # outlive the original it was supposed to stand next to.
            with contextlib.suppress(Exception):
                fs.delete_file(written.path)
            raise

        return IngestedDocument(
            path=written.path,
            title=written.title,
            description=written.description,
            converter=conversion.converter,
            raw_path=str(raw_target),
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
