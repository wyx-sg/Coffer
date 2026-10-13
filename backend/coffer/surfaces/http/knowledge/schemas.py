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

from typing import Any, Literal

from pydantic import BaseModel, Field

from coffer.application.knowledge.tidy_handoff import collection_tidy_prompt
from coffer.domain.knowledge.entry import CollectionEntry, FileEntry, Finding
from coffer.infrastructure.knowledge.tidy_runs import TIDY_RUNS
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
    #: tidy to the agent"); it carries the collection's mechanical findings.
    tidy_handoff: HandoffOut
    #: Whether an agent has a tidy of this collection open ("Record a tidy as
    #: one change"): its edits are committed as one change when it finishes.
    tidy_running: bool = False
    #: A linked folder the person keeps with their own tools ("Link a folder
    #: the person keeps themselves"): Coffer only shares it with the agents,
    #: so it has no tidy, check, history, upload or sync.
    linked: bool = False
    #: A linked folder's Markdown files; 0 for a collection Coffer keeps.
    note_count: int = 0
    #: A linked folder's own rules file at its root, empty when none.
    rules_file: str = ""


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
        tidy_running=TIDY_RUNS.get(entry.name) is not None,
        linked=entry.linked,
        note_count=entry.note_count,
        rules_file=entry.rules_file,
    )


FindingKind = Literal[
    "dead_link",
    "ambiguous_link",
    "outside_link",
    "duplicate_slug",
    "missing_source",
    "superseded_source",
    "incomplete_page",
    "unsourced_page",
    "stale_page",
    "orphan_page",
    "waiting_source",
]


class FindingOut(BaseModel):
    kind: FindingKind
    #: The file the finding concerns, knowledge-root-relative.
    path: str
    #: The link, slug or source it names; for ``incomplete_page`` the missing
    #: keys, comma-separated; for ``stale_page`` the ``verified`` date as
    #: written (``null`` when the page has none).
    target: str | None = None
    #: The other files a duplicate slug or an ambiguous link involves; for
    #: ``superseded_source`` the newest source that replaces the cited one.
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


class CollectionLink(BaseModel):
    #: The folder's absolute path on this machine.
    folder: str = Field(min_length=1, max_length=4096)
    #: The collection's label; the folder's own name when absent.
    name: str | None = Field(default=None, min_length=1, max_length=64)


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
    #: A source no page cites, none marks skipped and none superseded.
    waiting: bool = False
    #: A page due a recheck: its ``verified`` date missing or older than the
    #: collection's ``verify_after_days``.
    stale: bool = False
    #: A source's replacement: the path its ``superseded_by`` resolves to, or
    #: the slug itself when it names none; empty when it is current.
    superseded_by: str = ""
    #: A source's ``summary``.
    summary: str = ""
    #: How many pages cite a source, and whether it is marked ``ingest: skipped``.
    cited_count: int = 0
    skipped: bool = False


def file_summary_out(entry: FileEntry) -> FileSummaryOut:
    return FileSummaryOut.model_validate(entry, from_attributes=True)


class CollectionFilesOut(BaseModel):
    """Every page and source of one collection, for its page's Contents
    ("Show a collection's contents by page type")."""

    files: list[FileSummaryOut]


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
    #: What the link names: a ``[[link]]``'s target, or a Markdown link's
    #: relative path as written.
    target: str
    #: The knowledge path it resolves to; ``null`` when dead or ambiguous, or
    #: when it leaves the knowledge root.
    path: str | None = None
    ambiguous: bool = False
    #: ``wiki`` for ``[[target]]``, ``path`` for a link by relative path.
    kind: Literal["wiki", "path"] = "wiki"
    #: A relative link that climbs out of the knowledge root.
    outside: bool = False


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
    #: ("Link pages by slug or relative path and check every link").
    page_type: str = ""
    aliases: list[str] = Field(default_factory=list)
    #: A page's ``verified`` date, as written; empty when it carries none.
    verified: str = ""
    #: Whether the page is due a recheck (see ``FileSummaryOut.stale``).
    stale: bool = False
    sources: list[SourceRefOut] = Field(default_factory=list)
    links: list[LinkRefOut] = Field(default_factory=list)
    #: A source's citing pages and whether it waits ("Derive which sources
    #: wait from the pages that cite them").
    cited_by: list[PageRefOut] = Field(default_factory=list)
    waiting: bool = False
    #: A source's replacement, resolved; ``null`` when it is current.
    superseded_by: SourceRefOut | None = None
    #: A source's ``summary``.
    summary: str = ""
    #: An uploaded source's original file name; where it is on this Mac, or
    #: ``None`` when it was uploaded on another one.
    original: str = ""
    original_path: str | None = None
    #: The body as a reader should see it, when it differs from ``body``: a
    #: source that still carries an export's own frontmatter or Confluence
    #: storage markers, shown converted while the file stays as it is.
    readable_body: str | None = None
    #: Where an imported source came from: ``system``, ``title``, ``url``,
    #: ``page_id``, ``space``, ``version``, ``fetched_at``, ``raw``.
    origin: dict[str, str] = Field(default_factory=dict)
    #: An import's report as the source keeps it (``body``, ``complete``,
    #: ``attachments_kept``, ``missing``, ``unsupported``).
    import_report: dict[str, Any] = Field(default_factory=dict)


class ImportItemOut(BaseModel):
    """One attachment, embed or macro of an import, and how it ended."""

    name: str
    #: ``kept``, ``converted``, ``source_kept``, ``dropped``, ``missing``,
    #: ``unsupported`` or ``skipped``.
    status: str
    reason: str = ""
    #: Where it is kept, relative to the source, when it is.
    path: str = ""


class ImportReportOut(BaseModel):
    """What a structured import did, part by part (spec knowledge "Import a
    Confluence page as a readable source with its attachments")."""

    #: ``converted`` or ``partial``.
    body: str
    attachments: list[ImportItemOut] = Field(default_factory=list)
    macros: list[ImportItemOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    #: Nothing was left behind: the body whole, nothing missing or unsupported.
    complete: bool


class IngestedDocumentOut(BaseModel):
    #: The source the upload became (previewed: the path it would most likely get).
    path: str
    title: str
    description: str
    #: Which converter produced the Markdown.
    converter: str
    #: Part by part, what a structured import did; ``null`` for a plain file.
    report: ImportReportOut | None = None
    #: The page the upload is, by its system's id, when it says one.
    page_id: str = ""
    #: Older sources of the same page this import replaces (previewed: would).
    replaces: list[str] = Field(default_factory=list)
    #: Files kept beside the source, knowledge-root-relative.
    files: list[str] = Field(default_factory=list)
    #: Nothing was written: this is what the import would do.
    preview: bool = False
