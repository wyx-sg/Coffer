"""Wire models for ``/api/v1/knowledge/*``.

Every model here mirrors a value object from ``domain.knowledge.entry``. The
mirroring is deliberate rather than redundant: the domain types describe what
is on disk, and these describe what a client is promised — so removing a field
from the wire never means hiding one from the layer itself.

What is *absent* is the point of the current shape. There is no search request,
no search hit and no grep match, because this surface exposes no retrieval at
all (spec knowledge "No retrieval tool", FR-033): an agent reads the files with
its own tools at the paths its delivered skill carries, and the human reads
them through ``tree``/``file``. A model here would be a second retrieval
surface no one asked for.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CollectionOut(BaseModel):
    #: The collection's identity — what the curate route and every other
    #: collection-addressed route take. Carried on the list payload so a page
    #: can act on a row it has just rendered without a second lookup.
    uid: str
    #: A mutable label, and also the name of the directory on disk. Editable
    #: through PATCH, which moves the directory with it.
    name: str
    #: First paragraph of the collection's ``README.md`` (FR-011).
    description: str
    #: The two lanes are counted apart because they answer different questions:
    #: how much a person has contributed, and how much of it an agent can read
    #: today (FR-001). A collection with sources and no topics is one curation
    #: has not reached yet — a single total would hide exactly that.
    source_count: int = 0
    topic_count: int = 0


class CollectionListOut(BaseModel):
    collections: list[CollectionOut]


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str | None = None


class DirectoryOut(BaseModel):
    path: str
    name: str
    file_count: int


class FileSummaryOut(BaseModel):
    path: str
    title: str
    description: str
    actor: str
    updated_at: str


class TreeOut(BaseModel):
    path: str
    directories: list[DirectoryOut]
    files: list[FileSummaryOut]


class FileOut(BaseModel):
    path: str
    title: str
    description: str
    actor: str
    created_at: str
    updated_at: str
    body: str
    #: Absolute on-disk paths, so the UI can offer open / reveal (FR-041).
    file_path: str
    folder_path: str
    #: When curation last consumed this source; empty for a topic document and
    #: for a source no pass has reached yet (FR-028). It is what the page shows
    #: to answer "is this note in the topics yet?".
    ingested_at: str = ""


class FileWrite(BaseModel):
    title: str = Field(min_length=1)
    #: Required: the skill's catalogue is how a document is ever found, and a
    #: file that fails to describe itself is unfindable (FR-003).
    description: str = Field(min_length=1)
    body: str = ""
    #: Exactly one of ``collection`` or ``path``. ``collection`` (plus an
    #: optional ``folder`` inside it) creates a new source; ``path`` replaces
    #: the source already at that path. Neither names the ``sources/`` segment
    #: — the service adds it, so no caller can aim a write at ``topics/`` by
    #: spelling a path (FR-013, FR-021).
    #:
    #: Both are *filesystem* values and both stay names: the collection's name
    #: IS its directory under the knowledge root, so a uid here would be turned
    #: straight back into this string before a single byte could be written.
    #: The collection's uid addresses the collection itself — ``curate`` — and
    #: nothing on this route.
    collection: str | None = None
    folder: str | None = None
    path: str | None = None


class CurationRequest(BaseModel):
    #: One source to fold in, knowledge-root-relative. Omitted, the pass takes
    #: the oldest source whose ``coffer_ingested_at`` is behind its own
    #: modification time (FR-022) — which is what the page's "curate now"
    #: button wants, while a per-file trigger wants this.
    source: str | None = None


class CurationOut(BaseModel):
    #: ``ok`` | ``no_model`` | ``up_to_date`` | ``too_large`` | ``failed``.
    #: Every one of them is a 200: a collection with no model configured, or
    #: with nothing pending, is an ordinary state of the feature and not a
    #: fault of the request (FR-029).
    status: str
    #: The collection's NAME, not its uid. The caller sent the uid and still
    #: holds it; what a pass report adds is something to render — "curated
    #: shopee" — and that is the label (spec knowledge's contract,
    #: ``CurationOut.collection``).
    collection: str
    #: The source the pass took, when it took one.
    source: str = ""
    #: The internal model that ran it, so a surprising rewrite is traceable to
    #: a model rather than to Coffer.
    model: str = ""
    written: int = 0
    retired: int = 0
    #: Writes the pass refused — a topic naming another file (FR-027), or the
    #: eight-write bound (FR-025). Reported rather than swallowed, because a
    #: pass that hit its bound has more to absorb than it managed.
    refused: int = 0
    topics_before: int = 0
    topics_after: int = 0
    #: The source-size ceiling, present only with ``status`` ``too_large``.
    limit: int = 0


class IngestedDocumentOut(BaseModel):
    #: Path of the converted Markdown file, relative to the knowledge root.
    path: str
    title: str
    description: str
    #: Which converter produced this file.
    converter: str
    #: Path of the original the upload sent, relative to the knowledge root
    #: like ``path``: it is now an ordinary visible file in ``sources/`` beside
    #: the Markdown extracted from it (FR-016), so the surface that browses the
    #: lane can name it, which a hidden absolute location could not.
    original_path: str
