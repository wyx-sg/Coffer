"""Turning an uploaded document into a source for a collection.

An upload is one of the entrances new knowledge arrives by — the Knowledge page's upload
button and a channel attachment (see "Keep every upload as a Markdown source"
and "Ingest documents sent to a channel"). The document is converted to Markdown and
**submitted as material**: it goes through :meth:`KnowledgeService.submit`, which keeps
it as a source under ``sources/`` on the spot (see "Promote submitted material at
once"). The pictures the converter took out are kept beside it under ``assets/``,
in the same commit, and the uploaded file itself is kept on this Mac only (ADR
knowledge-sources-keep-their-images-and-originals-stay-on-this-mac).

What this module owns that ``submit`` does not need to think about: **the
description is optional input, never optional output.** The catalogue the
delivered skill carries is how an agent learns a document exists (see "Merge the
manual and the catalogue in the skill body"), so every upload gets a description,
drawn from its own opening prose (see "Fill frontmatter on converted material").

A structured import (a Confluence page) also brings: the keys its converter
read (where it came from, its version), the files it keeps beside the source
under ``assets/``, a report of every part, and the page's identity — so the
same page is not imported twice by accident, and importing it again on purpose
keeps the older source, marked replaced (spec knowledge "Import a Confluence
page as a readable source with its attachments").
"""

from __future__ import annotations

import asyncio
import logging
import pathlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from urllib.parse import quote

from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.knowledge.converter import (
    ITEM_KEPT,
    ITEM_MISSING,
    ITEM_UNSUPPORTED,
    Conversion,
    EmptyConversion,
    ImportReport,
)
from coffer.domain.knowledge.entry import ACTOR_USER
from coffer.domain.knowledge.errors import KnowledgeSourceExists, UploadTooLarge
from coffer.infrastructure.knowledge import assets, originals, paths, source_imports
from coffer.infrastructure.knowledge.naming import opening_prose, slugify

logger = logging.getLogger(__name__)


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

#: The converter that keeps a Markdown or text upload as it is.
PASSTHROUGH = "passthrough"
#: Keys Coffer writes on a source itself; an upload's own are never copied over them.
_OWNED_KEYS = frozenset(
    {
        "title",
        "description",
        "actor",
        "created_at",
        "updated_at",
        originals.ORIGINAL_KEY,
        originals.ORIGINAL_SHA_KEY,
        source_imports.SUPERSEDED_KEY,
    }
)
#: The frontmatter key a source keeps its import's report under.
REPORT_KEY = "import_report"


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
    #: Part by part, what a structured import did; ``None`` for a plain file.
    report: ImportReport | None = None
    #: The page the upload is, by its system's id, when it says one.
    page_id: str = ""
    #: The older sources of the same page this one replaces (or, previewed,
    #: would replace, or would be refused over without ``replace``).
    replaces: tuple[str, ...] = ()
    #: Files kept beside the source, knowledge-root-relative.
    files: tuple[str, ...] = field(default=())
    #: Nothing was written: this is what the import would do.
    preview: bool = False


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
        replace: bool = False,
        preview: bool = False,
    ) -> IngestedDocument:
        """Convert ``data`` (named ``filename``) and submit it as material.

        Raises ``UploadTooLarge`` over the size ceiling, ``UnsupportedDocument``
        (``domain.knowledge.converter``) for a type no converter handles,
        ``EmptyConversion`` when a converter ran and produced no text,
        ``KnowledgeSourceExists`` for a page already imported when ``replace``
        is not set, and whatever ``KnowledgeService.submit`` raises for an
        unknown or otherwise invalid target — in every one of those cases
        nothing is written, converted or kept (see "Bound uploads and leave
        nothing behind on failure"). With ``preview`` nothing is written
        either: the answer is what the import would do.
        """
        if len(data) > MAX_UPLOAD_BYTES:
            raise UploadTooLarge(len(data), MAX_UPLOAD_BYTES)

        # The same check `submit` itself makes, run here and up front so
        # a name that is not a collection is refused without first paying for
        # the conversion.
        row = await self._knowledge.require_collection(collection)

        conversion = await self._registry.convert(data, filename)
        # "Bound uploads and leave nothing behind on failure": a converter that succeeds
        # but extracts nothing (an image-only PDF is the real case) must not be stored
        # as a titled file with an empty body. Checked here rather than in each
        # converter so every format is covered by one rule.
        if not conversion.markdown.strip():
            raise EmptyConversion(pathlib.Path(filename).suffix.lstrip(".").lower())
        meta = dict(conversion.metadata)
        description = _description(meta, conversion.markdown, title=conversion.title)
        page_id = source_imports.page_id_of(meta)
        older = tuple(await asyncio.to_thread(source_imports.current, row.name, page_id))
        if older and not replace and not preview:
            raise KnowledgeSourceExists(page_id, older[0])

        sha = originals.digest(data)
        folder, body = await asyncio.to_thread(_free_folder, row.name, conversion, sha)
        files = {
            **assets.picture_paths(row.name, folder, conversion.images),
            **{
                f"{row.name}/{paths.ASSETS_DIR_NAME}/{folder}/{f.name}": f.data
                for f in conversion.files
            },
        }
        name = pathlib.PurePosixPath(filename).name or "upload"
        # A Markdown or text upload *is* its source: there is no other original,
        # unless converting it rewrote it (an export's markers expanded).
        keeps_original = conversion.converter != PASSTHROUGH or conversion.report is not None
        extra: dict[str, Any] = {k: v for k, v in meta.items() if k not in _OWNED_KEYS}
        if keeps_original:
            extra |= {originals.ORIGINAL_KEY: name, originals.ORIGINAL_SHA_KEY: sha}
        if conversion.report is not None:
            extra[REPORT_KEY] = report_summary(conversion.report)
        if preview:
            return IngestedDocument(
                path=f"{row.name}/{paths.SOURCES_DIR_NAME}/{slugify(conversion.title)}.md",
                title=conversion.title,
                description=description,
                converter=conversion.converter,
                report=conversion.report,
                page_id=page_id,
                replaces=older,
                files=tuple(files),
                preview=True,
            )

        submitted = await self._knowledge.submit(
            collection=collection,
            title=conversion.title,
            description=description,
            body=assets.link_pictures(body, folder, conversion.images),
            actor_kind=ACTOR_USER,
            actor=actor,
            extra=extra,
            files=files,
            supersede=older,
        )
        # After the source is in: a failure here loses the local copy, not the upload.
        try:
            if keeps_original:
                await asyncio.to_thread(originals.keep, data, name)
        except OSError:
            logger.warning("knowledge.original.not_kept", exc_info=True)
        return IngestedDocument(
            path=submitted.document.path,
            title=conversion.title,
            description=description,
            converter=conversion.converter,
            report=conversion.report,
            page_id=page_id,
            replaces=older,
            files=tuple(files),
        )


def report_summary(report: ImportReport) -> dict[str, Any]:
    """The part of an import's report a source keeps in its frontmatter: how
    the body ended and what was not kept, so a reader of the file alone can
    tell a partial import from a whole one."""
    items = (*report.attachments, *report.macros)
    summary: dict[str, Any] = {
        "body": report.body,
        "complete": report.complete,
        "attachments_kept": sum(1 for i in report.attachments if i.status == ITEM_KEPT),
    }
    for status in (ITEM_MISSING, ITEM_UNSUPPORTED):
        named = [
            f"{i.name}: {i.reason}" if i.reason else i.name for i in items if i.status == status
        ]
        if named:
            summary[status] = named
    return summary


def _free_folder(collection: str, conversion: Conversion, sha: str) -> tuple[str, str]:
    """The folder under ``assets/`` this upload's files go in, and its
    Markdown pointed there. A folder the converter named that is already
    taken (the same page and version imported again) gets a ``-2`` of its
    own, so no kept file is ever overwritten."""
    wanted = conversion.asset_folder or assets.folder_for(conversion.title, sha)
    base = paths.collection_dir(collection) / paths.ASSETS_DIR_NAME
    folder, n = wanted, 2
    while (conversion.files or conversion.images) and (base / folder).exists():
        folder, n = f"{wanted}-{n}", n + 1
    body = conversion.markdown
    if folder != wanted and conversion.asset_folder:
        prefix = f"../{paths.ASSETS_DIR_NAME}/"
        body = body.replace(prefix + quote(wanted) + "/", prefix + quote(folder) + "/")
    return folder, body


def _description(meta: Mapping[str, Any], markdown: str, *, title: str) -> str:
    """The description the upload carried (``description`` or ``summary``),
    else its own opening prose, else its title — never empty ("Carry title,
    description and actor in frontmatter" makes the description required)."""
    for key in ("description", "summary"):
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())
    return _fallback_description(markdown, title=title)


def _fallback_description(markdown: str, *, title: str) -> str:
    """The document's own opening prose, or its title — never empty ("Carry
    title, description and actor in frontmatter" makes the description required)."""
    return opening_prose(markdown, fallback=title)


__all__ = [
    "MAX_UPLOAD_BYTES",
    "REPORT_KEY",
    "IngestService",
    "IngestedDocument",
]
