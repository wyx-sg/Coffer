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
    #: Documents an agent can read today, and material still waiting in the
    #: inbox to be merged into them (FR-005) — counted apart because the second
    #: is exactly what an agent cannot see yet.
    document_count: int = 0
    pending_count: int = 0


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
    #: When curation last had this document in front of it; empty when it never
    #: has (FR-028). A document edited since is what the sweep comes back for.
    curated_at: str = ""


class MaterialIn(BaseModel):
    """New knowledge for a collection (FR-013)."""

    #: The collection's directory NAME: a filesystem value, like every path on
    #: this family — see the route module's docstring.
    collection: str = Field(min_length=1)
    title: str = Field(min_length=1)
    #: Required: the skill's catalogue is how a document is ever found, and
    #: material that fails to describe itself is unfindable (FR-003).
    description: str = Field(min_length=1)
    body: str = ""


class SubmissionOut(BaseModel):
    """What became of submitted material.

    ``status`` is ``pending`` when it waits in the inbox for a pass to merge,
    and ``written`` when it was promoted to a document on the spot because no
    internal model is configured (FR-029) — ``path`` is that document.
    """

    status: str
    collection: str
    title: str
    path: str | None = None


class CurationRequest(BaseModel):
    #: One document to carry through, knowledge-root-relative. Omitted, the
    #: pass takes the oldest pending item — inbox material first, then a
    #: document edited since curation last stamped it (FR-022) — which is what
    #: the page's "curate now" button wants.
    document: str | None = None


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
    #: The item the pass took, when it took one: an inbox item or a document.
    item: str = ""
    #: The internal model that ran it, so a surprising rewrite is traceable to
    #: a model rather than to Coffer.
    model: str = ""
    written: int = 0
    retired: int = 0
    #: Writes the pass refused — a document naming another file (FR-027), or the
    #: eight-write bound (FR-025). Reported rather than swallowed, because a
    #: pass that hit its bound has more to absorb than it managed.
    refused: int = 0
    documents_before: int = 0
    documents_after: int = 0
    #: The item-size ceiling, present only with ``status`` ``too_large``.
    limit: int = 0
    #: Documents the inbox was promoted into as it stood, present only with
    #: ``status`` ``no_model`` (FR-029).
    promoted: list[str] = Field(default_factory=list)


class IngestedDocumentOut(BaseModel):
    #: The document the upload became when it was promoted on the spot (no
    #: internal model to merge it); ``None`` while it waits to be merged.
    path: str | None = None
    title: str
    description: str
    #: Which converter produced the Markdown.
    converter: str
    #: True when the upload waits in the inbox for a pass to merge it.
    pending: bool
