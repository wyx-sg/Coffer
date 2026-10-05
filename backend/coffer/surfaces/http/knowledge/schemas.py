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

from pydantic import BaseModel, Field

from coffer.application.knowledge.tidy_handoff import collection_tidy_prompt
from coffer.domain.knowledge.entry import CollectionEntry
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
    #: Documents an agent can read.
    document_count: int = 0
    #: The collection directory's absolute path — what Reveal folder opens
    #: ("Return absolute paths on reads").
    folder_path: str = ""
    #: When a document in the collection was last written (ISO 8601, UTC);
    #: ``null`` when it holds none — the Overview's "edited today 13:30".
    updated_at: str | None = None
    #: The prompt that hands tidying this collection to the person's agent ("Hand a
    #: tidy to the person's agent").
    tidy_handoff: HandoffOut


def collection_out(entry: CollectionEntry) -> CollectionOut:
    return CollectionOut(
        uid=entry.uid,
        name=entry.name,
        description=entry.description,
        document_count=entry.document_count,
        folder_path=entry.folder_path,
        updated_at=entry.updated_at,
        tidy_handoff=HandoffOut(prompt=collection_tidy_prompt(entry)),
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
    #: Absolute on-disk paths, so the UI can offer open / reveal ("Return
    #: absolute paths on reads").
    file_path: str
    folder_path: str


class IngestedDocumentOut(BaseModel):
    #: The document the upload became.
    path: str
    title: str
    description: str
    #: Which converter produced the Markdown.
    converter: str
