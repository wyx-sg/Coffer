"""Wire shapes of ``/api/v1/vault`` (spec vault-storage "Show, compare and
restore any version of a vault file").

A version is one commit: every accepted write to the vault is one commit
naming its writer (ADR every-vault-write-is-a-validated-commit-naming-its-writer),
so a row of a file's history says who wrote it, for whom, on which machine,
and — for a restore — which version it put back.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from coffer.domain.vault.content_ids import fingerprint
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
    versions: list[VaultVersionOut]
    #: Pass as ``cursor`` for the next page; null on the last one.
    next_cursor: str | None


class VaultChangesOut(BaseModel):
    changes: list[VaultVersionOut]
    next_cursor: str | None


class VaultDiffOut(BaseModel):
    path: str
    version: str
    status: str
    #: The unified diff this version made to the file (empty for binary).
    diff: str
    added: int
    removed: int


class VaultContentOut(BaseModel):
    path: str
    #: The version read; null for the file as it is on disk now.
    version: str | None
    #: The text; empty when ``binary`` is true.
    content: str
    binary: bool
    size: int
    #: sha256 of the bytes — what a restore states as ``expected_fingerprint``.
    fingerprint: str


class VaultRestoreIn(BaseModel):
    #: A file, or a folder ending in ``/`` (restored whole: files the version
    #: did not have are removed).
    path: str = Field(min_length=1)
    version: str = Field(min_length=4)
    #: For a file: the fingerprint of the bytes last read (null when no file is
    #: there now). A mismatch is 409 ``VAULT_FILE_STALE``. Ignored for a
    #: folder, whose every file must match ``HEAD``.
    expected_fingerprint: str | None


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


def diff_out(diff: FileDiff, version: str) -> VaultDiffOut:
    return VaultDiffOut(
        path=diff.path,
        version=version,
        status=diff.status,
        diff=diff.diff,
        added=diff.added,
        removed=diff.removed,
    )


def content_out(path: str, version: str | None, data: bytes) -> VaultContentOut:
    try:
        text = data.decode("utf-8")
        binary = "\x00" in text
    except UnicodeDecodeError:
        text, binary = "", True
    return VaultContentOut(
        path=path,
        version=version,
        content="" if binary else text,
        binary=binary,
        size=len(data),
        fingerprint=fingerprint(data),
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
    "VaultChangesOut",
    "VaultContentOut",
    "VaultDiffOut",
    "VaultHistoryOut",
    "VaultPathChangeOut",
    "VaultProblemOut",
    "VaultProblemsOut",
    "VaultRestoreIn",
    "VaultRestoreOut",
    "VaultVersionOut",
    "content_out",
    "diff_out",
    "problem_out",
    "version_out",
]
