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
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import pathlib
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.knowledge.converter import Conversion, ConversionIssue, EmptyConversion
from coffer.domain.knowledge.entry import ACTOR_USER
from coffer.domain.knowledge.errors import KnowledgeFileNotFound, UploadTooLarge
from coffer.infrastructure.knowledge import assets, originals, paths
from coffer.infrastructure.knowledge.fs import timestamp
from coffer.infrastructure.knowledge.naming import opening_prose, slugify, unique_name

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

#: An upload's report: everything was kept, or something could not be.
STATUS_COMPLETE = "complete"
STATUS_PARTIAL = "partial"

#: An issue that leaves the import complete: the text is kept, only not drawn.
_NOT_PARTIAL = frozenset({"not_rendered"})

#: Frontmatter keys an import carries that the ingest fills in or reads.
RETRIEVED_AT_KEY = "retrieved_at"
REPRESENTATION_KEY = "representation"


@dataclass(frozen=True)
class IngestedDocument:
    """What one ingest produced — or, for a dry run, would produce.

    ``path`` is the source the upload became.
    """

    path: str
    title: str
    description: str
    #: Name of the converter that produced the Markdown (``Conversion.converter``).
    converter: str
    #: ``complete``, or ``partial`` when any issue other than ``not_rendered``.
    status: str = STATUS_COMPLETE
    #: The knowledge paths kept beside the source (its pictures and files).
    files: tuple[str, ...] = ()
    #: What the conversion could not keep or render.
    issues: tuple[ConversionIssue, ...] = ()
    #: The source this one replaces, now marked ``superseded_by`` it.
    replaced: str | None = None
    #: True when nothing was written.
    dry_run: bool = False


@dataclass(frozen=True)
class _Plan:
    """Everything the upload writes, worked out before anything is."""

    title: str
    description: str
    body: str
    extra: dict[str, Any]
    kept: tuple[str, ...]
    fresh: dict[str, bytes]
    keeps_original: bool
    name: str


def status_of(issues: tuple[ConversionIssue, ...]) -> str:
    """``partial`` when anything other than an unrendered diagram is missing."""
    return STATUS_PARTIAL if any(i.kind not in _NOT_PARTIAL for i in issues) else STATUS_COMPLETE


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
        replaces: str | None = None,
        dry_run: bool = False,
    ) -> IngestedDocument:
        """Convert ``data`` (named ``filename``) and submit it as material.

        ``replaces`` names a source of the same collection the new one replaces:
        it gains ``superseded_by`` in the same commit. ``dry_run`` converts and
        answers the same report, writing nothing.

        Raises ``UploadTooLarge`` over the size ceiling, ``UnsupportedDocument``
        (``domain.knowledge.converter``) for a type no converter handles,
        ``EmptyConversion`` when a converter ran and produced no text,
        ``KnowledgeFileNotFound`` when ``replaces`` is no source of the
        collection, and whatever ``KnowledgeService.submit`` raises for an
        unknown or otherwise invalid target — in every one of those cases
        nothing is written, converted or kept (see "Bound uploads and leave
        nothing behind on failure").
        """
        if len(data) > MAX_UPLOAD_BYTES:
            raise UploadTooLarge(len(data), MAX_UPLOAD_BYTES)

        # The same check `submit` itself makes, run here and up front so
        # a name that is not a collection is refused without first paying for
        # the conversion.
        row = await self._knowledge.require_collection(collection)
        replaced = _replaced_source(row.name, replaces) if replaces else None

        conversion = await self._registry.convert(data, filename)
        # "Bound uploads and leave nothing behind on failure": a converter that succeeds
        # but extracts nothing (an image-only PDF is the real case) must not be stored
        # as a titled file with an empty body. Checked here rather than in each
        # converter so every format is covered by one rule.
        if not conversion.markdown.strip():
            raise EmptyConversion(pathlib.Path(filename).suffix.lstrip(".").lower())
        plan = await asyncio.to_thread(_plan, row.name, conversion, filename, data)
        would_be = unique_name(paths.sources_dir(row.name), slugify(plan.title))
        report = IngestedDocument(
            path=f"{row.name}/{paths.SOURCES_DIR_NAME}/{would_be}",
            title=plan.title,
            description=plan.description,
            converter=conversion.converter,
            status=status_of(conversion.issues),
            files=plan.kept,
            issues=conversion.issues,
            replaced=replaced,
            dry_run=dry_run,
        )
        if dry_run:
            return report

        submitted = await self._knowledge.submit(
            collection=collection,
            title=plan.title,
            description=plan.description,
            body=plan.body,
            actor_kind=ACTOR_USER,
            actor=actor,
            extra=plan.extra,
            files=plan.fresh,
            supersedes=replaced,
        )
        # After the source is in: a failure here loses the local copy, not the upload.
        try:
            if plan.keeps_original:
                await asyncio.to_thread(originals.keep, data, plan.name)
        except OSError:
            logger.warning("knowledge.original.not_kept", exc_info=True)
        return dataclasses.replace(report, path=submitted.document.path)


def _replaced_source(collection: str, replaces: str) -> str:
    """The knowledge path of the source ``replaces`` names — written with or
    without its collection — refused unless it is a source of ``collection``."""
    relpath = replaces.strip().strip("/")
    if not relpath.startswith(f"{collection}/"):
        relpath = f"{collection}/{relpath}"
    if paths.kind_of(relpath) != paths.KIND_SOURCE or not paths.resolve(relpath).is_file():
        raise KnowledgeFileNotFound(relpath)
    return relpath


def _plan(collection: str, conversion: Conversion, filename: str, data: bytes) -> _Plan:
    """What the upload writes: its frontmatter, its body with every kept file
    linked where it lands, and the files not already kept there."""
    metadata: dict[str, Any] = dict(conversion.metadata)
    title = conversion.title
    metadata.pop("title", None)
    given = metadata.pop("description", None)
    sha = originals.digest(data)
    kept_bytes: dict[str, bytes] = {image.name: image.data for image in conversion.images}
    kept_bytes.update({file.name: file.data for file in conversion.files})
    folder, fresh = assets.place(
        collection, conversion.asset_folder or assets.folder_for(title, sha), kept_bytes, sha
    )
    names = frozenset(kept_bytes)
    body = assets.link_pictures(conversion.markdown, folder, conversion.images)
    body = assets.link_assets(body, folder, names)
    extra: dict[str, Any] = assets.link_values(metadata, folder, names)
    # Drawn from the body as written, its kept files already linked.
    description = (given.strip() if isinstance(given, str) else "") or _fallback_description(
        body, title=title
    )
    if REPRESENTATION_KEY in extra:
        # An import from another system says when it was taken.
        extra.setdefault(RETRIEVED_AT_KEY, timestamp())
    name = pathlib.PurePosixPath(filename).name or "upload"
    # A Markdown or text upload *is* its source: there is no other original —
    # unless its converter says otherwise (a file whose markers were expanded).
    keeps = (
        conversion.keeps_original
        if conversion.keeps_original is not None
        else conversion.converter != PASSTHROUGH
    )
    if keeps:
        extra.update({originals.ORIGINAL_KEY: name, originals.ORIGINAL_SHA_KEY: sha})
    prefix = f"{collection}/{paths.ASSETS_DIR_NAME}/{folder}"
    return _Plan(
        title=title,
        description=description,
        body=body,
        extra=extra,
        kept=tuple(f"{prefix}/{n}" for n in kept_bytes),
        fresh=fresh,
        keeps_original=keeps,
        name=name,
    )


def _fallback_description(markdown: str, *, title: str) -> str:
    """The document's own opening prose, or its title — never empty ("Carry
    title, description and actor in frontmatter" makes the description required)."""
    return opening_prose(markdown, fallback=title)


__all__ = [
    "MAX_UPLOAD_BYTES",
    "STATUS_COMPLETE",
    "STATUS_PARTIAL",
    "IngestService",
    "IngestedDocument",
    "status_of",
]
