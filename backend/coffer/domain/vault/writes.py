"""The value types of the vault's one write path (spec vault-storage).

The writer itself — the lock, the compare-and-swap, the commit — is in
``coffer.infrastructure.vault.writer``; these are the shapes every caller and
every validator exchanges with it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath
from typing import Protocol

from coffer.domain.vault.content_ids import fingerprint
from coffer.domain.vault.errors import VaultPathRefused
from coffer.domain.vault.findings import Finding
from coffer.domain.vault.writers import CommitMeta


class Expect(Enum):
    """What a write expects the file to hold, when not a fingerprint."""

    #: Whatever ``HEAD`` holds: no unsettled hand edit is in the way.
    HEAD = "head"
    #: The file must not exist.
    ABSENT = "absent"


@dataclass(frozen=True)
class Change:
    """One path of a pending commit, for the validator."""

    path: str
    #: The bytes about to be committed; ``None`` for a deletion.
    data: bytes | None
    #: The bytes at ``HEAD``; ``None`` for a new file.
    before: bytes | None


@dataclass(frozen=True)
class Fix:
    """A correction the validator asks the daemon to commit after a person's
    edit — a uid minted for a hand-made resource file."""

    path: str
    data: bytes
    summary: str


@dataclass(frozen=True)
class Verdict:
    findings: list[Finding] = field(default_factory=list)
    fixes: list[Fix] = field(default_factory=list)


class TreeReader(Protocol):
    """What a validator may read of the vault's history: ``HEAD`` and any
    other commit, never the working tree it is judging."""

    def read(self, ref: str, path: str) -> bytes | None: ...

    def tree(self, ref: str = "HEAD", prefix: str = "") -> dict[str, str]: ...


Validator = Callable[[Sequence[Change], TreeReader], Verdict]


@dataclass(frozen=True)
class CommitResult:
    version: str
    meta: CommitMeta
    paths: tuple[str, ...]


Listener = Callable[[CommitResult], None]


@dataclass(frozen=True)
class Snapshot:
    """A file as a writer read it."""

    path: str
    data: bytes | None

    @property
    def fingerprint(self) -> str | None:
        return fingerprint(self.data) if self.data is not None else None


def accept_all(_changes: Sequence[Change], _repo: TreeReader) -> Verdict:
    return Verdict()


def check_path(path: str) -> str:
    """``path`` if it is a plain vault-relative path; refuse anything else."""
    pure = PurePosixPath(path)
    if (
        not path
        or pure.is_absolute()
        or "\\" in path
        or any(part in ("", ".", "..", ".git") for part in path.split("/"))
    ):
        raise VaultPathRefused(f"not a vault path: {path!r}")
    return str(pure)


__all__ = [
    "Change",
    "CommitResult",
    "Expect",
    "Fix",
    "Listener",
    "Snapshot",
    "TreeReader",
    "Validator",
    "Verdict",
    "accept_all",
    "check_path",
]
