"""Value objects for the knowledge layer.

Everything here describes what is on disk. Nothing is persisted: a catalogue
level is produced by walking the directory at call time (spec knowledge
FR-020), so these types are the shape of an answer, never the shape of a row.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ACTOR_AGENT = "agent"
ACTOR_USER = "user"


@dataclass(frozen=True)
class CollectionEntry:
    """One collection, as the top level of the catalogue shows it."""

    name: str
    #: First paragraph of the collection's ``README.md``; empty when absent.
    description: str
    file_count: int


@dataclass(frozen=True)
class DirectoryEntry:
    """A subdirectory inside a collection — the human's own filing."""

    #: Path relative to the knowledge root, e.g. ``shopee/account``.
    path: str
    name: str
    file_count: int


@dataclass(frozen=True)
class FileEntry:
    """A file as the catalogue lists it: enough to choose without reading."""

    #: Path relative to the knowledge root, e.g. ``shopee/account/gateway.md``.
    path: str
    title: str
    description: str
    actor: str
    updated_at: str


@dataclass(frozen=True)
class CatalogueLevel:
    """One level of the catalogue — never the whole tree (FR-021)."""

    path: str
    directories: tuple[DirectoryEntry, ...] = field(default_factory=tuple)
    files: tuple[FileEntry, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class KnowledgeFile:
    """A file's full content plus the on-disk truth a surface must expose."""

    path: str
    title: str
    description: str
    actor: str
    created_at: str
    updated_at: str
    body: str
    #: Absolute path of the ``.md`` file (spec knowledge FR-062).
    file_path: str
    #: Absolute path of its containing folder.
    folder_path: str


@dataclass(frozen=True)
class GrepMatch:
    path: str
    line_number: int
    line: str


@dataclass(frozen=True)
class GrepOutcome:
    matches: tuple[GrepMatch, ...] = field(default_factory=tuple)
    truncated: bool = False
