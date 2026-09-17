"""Value objects for the knowledge layer.

Everything here describes what is on disk. Nothing is persisted: a catalogue
is produced by walking the directory at call time, so these types are the
shape of an answer, never the shape of a row.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ACTOR_AGENT = "agent"
ACTOR_USER = "user"


@dataclass(frozen=True)
class CollectionEntry:
    """One collection, as the top level of the catalogue shows it.

    The two lanes are counted apart because they answer different questions:
    how much material a person has contributed, and how much of it an agent
    can currently read (spec knowledge FR-001).
    """

    name: str
    #: First paragraph of the collection's ``README.md``; empty when absent.
    description: str
    source_count: int = 0
    topic_count: int = 0


@dataclass(frozen=True)
class DirectoryEntry:
    """A subdirectory inside a lane — the person's filing, or curation's."""

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
    """One level of one lane — what a human surface pages through."""

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
    #: Absolute path of the ``.md`` file (spec knowledge FR-041).
    file_path: str
    #: Absolute path of its containing folder.
    folder_path: str
    #: When curation last consumed this source; empty for a topic (FR-028).
    ingested_at: str = ""


@dataclass(frozen=True)
class GrepMatch:
    path: str
    line_number: int
    line: str


@dataclass(frozen=True)
class GrepOutcome:
    matches: tuple[GrepMatch, ...] = field(default_factory=tuple)
    truncated: bool = False
