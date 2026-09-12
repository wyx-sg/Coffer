"""Wire models for ``/api/v1/knowledge/*``.

Every model here mirrors a value object from ``domain.knowledge.entry``. The
mirroring is deliberate rather than redundant: the domain types describe what
is on disk, and these describe what a client is promised — so removing a field
from the wire never means hiding one from the layer itself.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CollectionOut(BaseModel):
    name: str
    description: str
    file_count: int


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
    #: Absolute on-disk paths, so the UI can offer open / reveal (FR-062).
    file_path: str
    folder_path: str


class FileWrite(BaseModel):
    title: str = Field(min_length=1)
    #: Required: with no ranked index, the catalogue is the retrieval surface
    #: and a file that fails to describe itself is unfindable (FR-003).
    description: str = Field(min_length=1)
    body: str = ""
    #: Exactly one of these. ``directory`` creates a new file there;
    #: ``path`` replaces the file at that path.
    directory: str | None = None
    path: str | None = None


class GrepMatchOut(BaseModel):
    path: str
    line_number: int
    line: str


class GrepOut(BaseModel):
    matches: list[GrepMatchOut]
    truncated: bool


class TidyOut(BaseModel):
    status: str
    collection: str
    merged: int = 0
    rewritten: int = 0
