"""Wire shapes of ``/api/v1/vault`` (spec vault-storage "Show and restore any
version of a vault file or folder", "List the hand edits the vault kept out").

A version is one commit: every accepted write to the vault is one commit
naming its writer (ADR every-vault-write-is-a-validated-commit-naming-its-writer),
so a row of a file's history says who wrote it, for whom, on which machine,
and — for a restore — which version it put back.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from coffer.domain.vault.findings import Finding
from coffer.domain.vault.history import Commit, FileDiff, PathChange
from coffer.domain.vault.writers import display_writer


class VaultPathChangeOut(BaseModel):
    """One file a version touched, with its line counts (0/0 for binary)."""

    path: str
    #: ``added`` | ``modified`` | ``removed``
    status: str
    added: int
    removed: int


class VaultVersionOut(BaseModel):
    """One version of a file or folder: the commit that produced it."""

    version: str
    time: datetime
    #: ``user`` | ``disk`` | ``agent`` | ``daemon`` | ``curation`` | ``sync``
    writer: str
    #: The label a history row shows: ``agent:<type>`` for an agent, else the writer.
    display_writer: str
    actor: str | None
    machine: str | None
    summary: str
    operation: str
    #: The version a restore put back; null for any other write.
    restored_from: str | None
    #: True when this version removed the file (a file's history only).
    removed: bool = False
    #: The files this version touched — for a folder, only those inside it.
    paths: list[VaultPathChangeOut] = Field(default_factory=list)


class VaultHistoryOut(BaseModel):
    #: The file, or the folder (ending in ``/``), the history is of.
    path: str
    #: Newest first; the first is the path as it is now.
    versions: list[VaultVersionOut]
    #: Pass as ``cursor`` for the next page; null on the last one.
    next_cursor: str | None


class VaultFileDiffOut(BaseModel):
    """One file's unified diff (empty for binary)."""

    path: str
    #: ``added`` | ``modified`` | ``removed``
    status: str
    diff: str
    added: int
    removed: int


class VaultDiffOut(BaseModel):
    path: str
    version: str
    #: ``previous``: what this version changed; ``current``: from this
    #: version to the path as it is now.
    against: Literal["previous", "current"]
    files: list[VaultFileDiffOut]


class VaultRestoreIn(BaseModel):
    #: A file, or a folder ending in ``/`` (restored whole: files the version
    #: did not have are removed).
    path: str = Field(min_length=1)
    version: str = Field(min_length=4)
    #: The newest version the caller saw in the path's history. When the path
    #: changed since, the restore is 409 ``VAULT_FILE_STALE`` and writes
    #: nothing. Null skips the check.
    expected_current: str | None = None


class VaultRestoreOut(BaseModel):
    path: str
    #: The new commit; null when the content already matched the version.
    version: str | None
    restored_from: str
    #: Every file the restore wrote or removed.
    paths: list[str]


class VaultProblemOut(BaseModel):
    """A hand edit validation refused: on disk, uncommitted, not in effect."""

    path: str
    code: str
    message: str
    #: The resource the file is about, when it names one.
    uid: str | None
    #: ``error`` (kept out of ``HEAD``) or ``warning``.
    severity: str


class VaultProblemsOut(BaseModel):
    problems: list[VaultProblemOut]


def _change_out(change: PathChange) -> VaultPathChangeOut:
    return VaultPathChangeOut(
        path=change.path, status=change.status, added=change.added, removed=change.removed
    )


def version_out(commit: Commit, *, within: str = "", removed: bool = False) -> VaultVersionOut:
    """``commit`` as a history row; ``within`` (a folder ending in ``/``, or a
    file) narrows the files listed to that part of the vault."""

    def inside(path: str) -> bool:
        if not within:
            return True
        return path.startswith(within) if within.endswith("/") else path == within

    meta = commit.meta
    return VaultVersionOut(
        version=commit.version,
        time=commit.time,
        writer=meta.writer,
        display_writer=display_writer(meta),
        actor=meta.actor,
        machine=meta.machine,
        summary=meta.summary,
        operation=meta.operation,
        restored_from=meta.restored_from,
        removed=removed,
        paths=[_change_out(p) for p in commit.paths if inside(p.path)],
    )


def file_diff_out(diff: FileDiff) -> VaultFileDiffOut:
    return VaultFileDiffOut(
        path=diff.path,
        status=diff.status,
        diff=diff.diff,
        added=diff.added,
        removed=diff.removed,
    )


def problem_out(finding: Finding) -> VaultProblemOut:
    return VaultProblemOut(
        path=finding.path,
        code=finding.code.value,
        message=finding.message,
        uid=finding.uid,
        severity=finding.severity.value,
    )


__all__ = [
    "VaultDiffOut",
    "VaultFileDiffOut",
    "VaultHistoryOut",
    "VaultPathChangeOut",
    "VaultProblemOut",
    "VaultProblemsOut",
    "VaultRestoreIn",
    "VaultRestoreOut",
    "VaultVersionOut",
    "file_diff_out",
    "problem_out",
    "version_out",
]
