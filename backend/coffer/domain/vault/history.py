"""What the vault's history answers (spec vault-storage).

Every accepted write is one commit naming its writer, so the history of any
vault file is ``git log`` over it. These are the shapes a surface reads back:
one commit as a :class:`Commit`, the files it touched as :class:`PathChange`,
one file's version as :class:`FileVersion`. Nothing here is persisted: git is
the record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from coffer.domain.vault.writers import CommitMeta

ADDED = "added"
MODIFIED = "modified"
REMOVED = "removed"


@dataclass(frozen=True)
class PathChange:
    """One file a commit touched, with its line counts (0/0 for binary)."""

    path: str
    status: str
    added: int = 0
    removed: int = 0


@dataclass(frozen=True)
class Commit:
    """One commit of the vault's history."""

    version: str
    time: datetime
    meta: CommitMeta
    paths: tuple[PathChange, ...] = field(default_factory=tuple)
    parents: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FileVersion:
    """One version of one file: the commit that produced it."""

    commit: Commit
    path: str
    #: True when this commit removed the file.
    removed: bool = False


@dataclass(frozen=True)
class FileDiff:
    """What one commit did to one file, as a unified diff."""

    path: str
    status: str
    diff: str
    added: int = 0
    removed: int = 0


def looks_like_a_version(version: str) -> bool:
    """A commit id, and nothing git would read as an option or a range."""
    return 4 <= len(version) <= 64 and all(c in "0123456789abcdef" for c in version)


__all__ = [
    "ADDED",
    "MODIFIED",
    "REMOVED",
    "Commit",
    "FileDiff",
    "FileVersion",
    "PathChange",
    "looks_like_a_version",
]
