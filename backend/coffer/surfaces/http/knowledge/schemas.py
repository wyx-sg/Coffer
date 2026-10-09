"""Wire models for ``/api/v1/knowledge/*``.

Every model here mirrors a value object from ``domain.knowledge.entry``. The
mirroring is deliberate rather than redundant: the domain types describe what
is on disk, and these describe what a client is promised — so removing a field
from the wire never means hiding one from the layer itself.

What is *absent* is the point of the current shape. There is no search request,
no search hit and no grep match, because this surface exposes no retrieval at
all (spec knowledge "Expose no knowledge tool"): an agent reads the
files with
its own tools at the paths its delivered skill carries, and the human reads
them through ``tree``/``file``. A model here would be a second retrieval
surface no one asked for.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from coffer.application.knowledge.tidy_handoff import (
    collection_check_prompt,
    collection_tidy_prompt,
)
from coffer.domain.knowledge.entry import CollectionEntry, Finding
from coffer.surfaces.http.handoff_schemas import HandoffOut


class CollectionOut(BaseModel):
    #: The collection's identity — what every collection-addressed route takes. Carried on the list
    #: payload so a page can act on a row it has just rendered without a second lookup.
    uid: str
    #: A mutable label, and also the name of the directory on disk. Editable
    #: through PATCH, which moves the directory with it.
    name: str
    #: First paragraph of the collection's ``README.md`` ("Read a collection's
    #: description from its README").
    description: str
    #: Pages under ``pages/`` and sources under ``sources/`` ("Keep sources and
    #: pages apart in each collection").
    page_count: int = 0
    source_count: int = 0
    #: Sources no page cites and none marks skipped ("Derive which sources wait
    #: from the pages that cite them").
    waiting_source_count: int = 0
    #: Mechanical findings, as ``/check`` lists them ("Check a collection
    #: mechanically on every read").
    finding_count: int = 0
    #: The collection directory's absolute path — what Reveal folder opens
    #: ("Return absolute paths on reads").
    folder_path: str = ""
    #: When a document in the collection was last written (ISO 8601, UTC);
    #: ``null`` when it holds none — the Overview's "edited today 13:30".
    updated_at: str | None = None
    #: The prompt that hands tidying this collection to the person's agent ("Hand a
    #: tidy to the person's agent").
    tidy_handoff: HandoffOut
    #: The prompt that hands a report-only check of this collection to the
    #: person's agent ("Hand a check to the agent").
    check_handoff: HandoffOut


def collection_out(entry: CollectionEntry) -> CollectionOut:
    return CollectionOut(
        uid=entry.uid,
        name=entry.name,
        description=entry.description,
        page_count=entry.page_count,
        source_count=entry.source_count,
        waiting_source_count=entry.waiting_source_count,
        finding_count=entry.finding_count,
        folder_path=entry.folder_path,
        updated_at=entry.updated_at,
        tidy_handoff=HandoffOut(prompt=collection_tidy_prompt(entry)),
        check_handoff=HandoffOut(prompt=collection_check_prompt(entry)),
    )


FindingKind = Literal[
    "dead_link",
    "ambiguous_link",
    "duplicate_slug",
    "missing_source",
    "incomplete_page",
    "unsourced_page",
    "orphan_page",
    "waiting_source",
]


class FindingOut(BaseModel):
    kind: FindingKind
    #: The file the finding concerns, knowledge-root-relative.
    path: str
    #: The link, slug or source it names; for ``incomplete_page`` the missing
    #: keys, comma-separated.
    target: str | None = None
    #: The other files a duplicate slug or an ambiguous link involves.
    others: list[str] = Field(default_factory=list)


class CheckOut(BaseModel):
    """One collection's mechanical check ("Check a collection mechanically on
    every read"): what Coffer found, and the prompt that hands the rest to the
    agent."""

    collection: CollectionOut
    findings: list[FindingOut]


def finding_out(finding: Finding) -> FindingOut:
    return FindingOut(
        kind=finding.kind,  # type: ignore[arg-type]
        path=finding.path,
        target=finding.target,
        others=list(finding.others),
    )


def check_out(entry: CollectionEntry) -> CheckOut:
    return CheckOut(
        collection=collection_out(entry), findings=[finding_out(f) for f in entry.findings]
    )


class CollectionListOut(BaseModel):
    collections: list[CollectionOut]


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str | None = None


class DirectoryOut(BaseModel):
    path: str
    name: str
    file_count: int


FileKind = Literal["page", "source", "file"]


class FileSummaryOut(BaseModel):
    path: str
    title: str
    description: str
    actor: str
    updated_at: str
    #: ``page`` under ``pages/``, ``source`` under ``sources/``, else ``file``.
    kind: FileKind = "file"
    #: A page's ``type``; empty otherwise.
    page_type: str = ""
    #: A source no page cites and none marks skipped.
    waiting: bool = False


class TreeOut(BaseModel):
    path: str
    directories: list[DirectoryOut]
    files: list[FileSummaryOut]


class SourceRefOut(BaseModel):
    #: The slug the page's ``sources`` entry names.
    slug: str
    #: The source it resolves to; ``null`` when no source has that slug.
    path: str | None = None
    title: str = ""


class LinkRefOut(BaseModel):
    #: What the ``[[link]]`` names.
    target: str
    #: The page or source it resolves to; ``null`` when dead or ambiguous.
    path: str | None = None
    ambiguous: bool = False


class PageRefOut(BaseModel):
    path: str
    title: str


class FileOut(BaseModel):
    path: str
    title: str
    description: str
    actor: str
    created_at: str
    updated_at: str
    body: str
    #: Absolute on-disk paths, so the UI can offer open / reveal ("Return
    #: absolute paths on reads").
    file_path: str
    folder_path: str
    kind: FileKind = "file"
    #: A page's ``type``, ``aliases``, resolved ``sources`` and ``[[links]]``
    #: ("Link pages by slug and check every link").
    page_type: str = ""
    aliases: list[str] = Field(default_factory=list)
    sources: list[SourceRefOut] = Field(default_factory=list)
    links: list[LinkRefOut] = Field(default_factory=list)
    #: A source's citing pages, whether it waits, and its kept original's
    #: absolute path ("Keep every upload as a source with its original").
    cited_by: list[PageRefOut] = Field(default_factory=list)
    waiting: bool = False
    original_path: str | None = None


class IngestedDocumentOut(BaseModel):
    #: The source the upload became.
    path: str
    title: str
    description: str
    #: Which converter produced the Markdown.
    converter: str
