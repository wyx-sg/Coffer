"""Read and restore the history of a vault file or folder (spec vault-storage
"Show and restore any version of a vault file or folder").

Every accepted write is a commit naming its writer, so the history of a file —
a knowledge document — or of a folder — one skill's master folder — is the
commits that touched it, newest first. A read first commits what changed on
disk under the path as a ``disk`` write, so the newest version is the file as
it is. Restoring a version is an ordinary write of that version's bytes
through the one write path: validated like any other write, refused when the
path changed since the caller read its history, and landed as a new commit
naming the writer and ``Coffer-Restored-From``. History is never rewritten.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from coffer.application.vault.ports import VaultHistoryPort, VaultWriterPort
from coffer.domain.error_base import CofferError
from coffer.domain.vault.errors import VaultFileStale, VaultPathRefused
from coffer.domain.vault.history import (
    ADDED,
    MODIFIED,
    REMOVED,
    Commit,
    FileDiff,
    FileVersion,
    looks_like_a_version,
)
from coffer.domain.vault.layout import SECRET
from coffer.domain.vault.writers import OP_RESTORE, WRITER_USER, CommitMeta
from coffer.domain.vault.writes import Expect, check_path

logger = logging.getLogger(__name__)

MAX_PAGE = 200

#: What a version's diff is read against: the version before it, or the
#: path as it is now.
Against = Literal["previous", "current"]


class VaultVersionNotFound(CofferError):  # noqa: N818
    """No such commit, or the path did not exist in it. Maps to 404."""

    code = "VAULT_VERSION_NOT_FOUND"


@dataclass(frozen=True)
class HistoryPage:
    path: str
    versions: tuple[FileVersion, ...]
    next_cursor: str | None


@dataclass(frozen=True)
class VersionDiff:
    path: str
    version: str
    against: Against
    #: One diff per file, in path order.
    files: tuple[FileDiff, ...]


@dataclass(frozen=True)
class Restored:
    path: str
    version: str | None
    restored_from: str
    #: Every file the restore wrote or removed (one for a file, many for a folder).
    paths: tuple[str, ...]


Recorder = Callable[[Restored, str], Awaitable[None]]


class VaultHistoryService:
    def __init__(
        self,
        history: VaultHistoryPort,
        writer: VaultWriterPort,
        *,
        on_restored: Recorder | None = None,
    ) -> None:
        self._history = history
        self._writer = writer
        self._on_restored = on_restored

    async def versions(
        self, path: str, *, limit: int = 50, cursor: str | None = None
    ) -> HistoryPage:
        """The commits that touched ``path`` (a file, or a folder ending in
        ``/``), newest first, one page at a time."""
        spec = _spec(path)
        limit = max(1, min(limit, MAX_PAGE))
        skip = _skip(cursor)
        await asyncio.to_thread(self._settle, spec)
        commits = await asyncio.to_thread(
            self._history.log, _pathspec(spec), limit=limit + 1, skip=skip
        )
        more = len(commits) > limit
        versions = tuple(_version(c, spec) for c in commits[:limit])
        return HistoryPage(spec, versions, str(skip + limit) if more else None)

    async def diff(self, path: str, version: str, against: Against = "previous") -> VersionDiff:
        """What ``version`` did to ``path`` (``previous``), or how ``path``
        differs now from how ``version`` left it (``current``), file by file."""
        spec = _spec(path)
        sha = _version_id(version)
        if against == "current":
            await asyncio.to_thread(self._settle, spec)
            files = await asyncio.to_thread(self._against_current, spec, sha)
        else:
            files = await asyncio.to_thread(self._own_change, spec, sha)
        return VersionDiff(spec, version, against, files)

    def _own_change(self, spec: str, sha: str) -> tuple[FileDiff, ...]:
        commit = self._history.commit_of(sha)
        if commit is None:
            raise VaultVersionNotFound(f"no version {sha}")
        changed = [p for p in commit.paths if _inside(spec, p.path)]
        if not changed:
            raise VaultVersionNotFound(f"{sha} did not change {spec}")
        return tuple(
            FileDiff(
                p.path, p.status, self._history.diff(commit.version, p.path), p.added, p.removed
            )
            for p in sorted(changed, key=lambda p: p.path)
        )

    def _against_current(self, spec: str, sha: str) -> tuple[FileDiff, ...]:
        commit = self._history.commit_of(sha)
        if commit is None:
            raise VaultVersionNotFound(f"no version {sha}")
        then = self._history.tree(commit.version, _pathspec(spec))
        now = self._history.tree("HEAD", _pathspec(spec))
        out: list[FileDiff] = []
        for file in sorted(set(then) | set(now)):
            if not _inside(spec, file) or then.get(file) == now.get(file):
                continue
            status = ADDED if file not in then else REMOVED if file not in now else MODIFIED
            text = self._history.diff_trees(commit.version, "HEAD", file)
            added, removed = _counts(text)
            out.append(FileDiff(file, status, text, added, removed))
        return tuple(out)

    async def restore(
        self,
        path: str,
        version: str,
        *,
        expected_current: str | None,
        actor: str,
        writer: str = WRITER_USER,
        agent: str | None = None,
    ) -> Restored:
        """Write ``version``'s content of ``path`` back as a new commit.

        ``expected_current`` is the newest version the caller saw in the
        path's history; when a later commit touched the path — or the path was
        edited on disk since — the restore is refused ``VAULT_FILE_STALE`` and
        writes nothing. For a folder (``path`` ending in ``/``) the files the
        version did not have are removed.
        """
        spec = _spec(path)
        sha = _version_id(version)
        await asyncio.to_thread(self._settle, spec)
        result = await asyncio.to_thread(
            self._restore_sync, spec, sha, expected_current, actor, writer, agent
        )
        if self._on_restored is not None:
            await self._on_restored(result, actor)
        return result

    def _restore_sync(
        self,
        spec: str,
        sha: str,
        expected_current: str | None,
        actor: str,
        writer: str,
        agent: str | None,
    ) -> Restored:
        commit = self._history.commit_of(sha)
        if commit is None:
            raise VaultVersionNotFound(f"no version {sha}")
        meta = CommitMeta(
            writer=writer,
            operation=OP_RESTORE,
            summary=f"Restored {spec} to {commit.version[:7]}",
            actor=actor,
            agent=agent,
            restored_from=commit.version,
        )
        with self._writer.begin(meta) as txn:
            if expected_current is not None:
                newest = self._history.log(_pathspec(spec), limit=1)
                if not newest or newest[0].version != expected_current:
                    raise VaultFileStale(
                        spec,
                        f"{spec} changed since its history was read; read it again and retry",
                    )
            then = self._history.tree(commit.version, _pathspec(spec))
            now = self._history.tree("HEAD", _pathspec(spec))
            for file in sorted(set(then) | set(now)):
                if not _inside(spec, file):
                    continue
                data = self._history.read(commit.version, file) if file in then else None
                if data is None:
                    txn.delete(file, Expect.HEAD)
                elif self._writer.read_disk(file) != data:
                    txn.write(file, data, Expect.HEAD if file in now else Expect.ABSENT)
            touched = tuple(txn.paths)
        return Restored(spec, txn.version, commit.version, touched)

    def _settle(self, spec: str) -> None:
        """Commit what changed on disk under ``spec`` outside any Coffer
        operation, as a ``disk`` write, so the history ends at the file as it
        is. A hand edit validation refuses stays out, as everywhere."""
        try:
            pending = [p for p in self._writer.pending() if _inside(spec, p)]
            if pending:
                self._writer.settle(pending)
        except Exception:
            logger.warning("vault.history.settle_failed", exc_info=True)


def _spec(path: str) -> str:
    """``path`` as a vault-relative file, or a folder ending in ``/``; refuse
    anything outside the vault and everything under ``secret/``. Rolling a
    secret back is re-entering it (ADR
    every-vault-write-is-a-validated-commit-naming-its-writer, "Secrets when
    not carried"), so its files are neither shown nor restored through
    history."""
    folder = path.endswith("/")
    clean = check_path(path.rstrip("/"))
    if clean == SECRET or clean.startswith(f"{SECRET}/"):
        raise VaultPathRefused(f"{SECRET}/ is not read or restored through history")
    return clean + "/" if folder else clean


def _pathspec(spec: str) -> str:
    return spec.rstrip("/") or "."


def _inside(spec: str, path: str) -> bool:
    return path.startswith(spec) if spec.endswith("/") else path == spec


def _version_id(version: str) -> str:
    if not looks_like_a_version(version):
        raise VaultVersionNotFound(f"not a version: {version!r}")
    return version


def _skip(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        return max(0, int(cursor))
    except ValueError:
        return 0


def _counts(diff: str) -> tuple[int, int]:
    """Added and removed lines of a unified diff (0/0 for binary)."""
    added = removed = 0
    for line in diff.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed


def _version(commit: Commit, spec: str) -> FileVersion:
    if spec.endswith("/"):
        return FileVersion(commit, spec, removed=False)
    change = next((p for p in commit.paths if p.path == spec), None)
    return FileVersion(commit, spec, removed=change is not None and change.status == REMOVED)


__all__ = [
    "Against",
    "HistoryPage",
    "Restored",
    "VaultHistoryService",
    "VaultVersionNotFound",
    "VersionDiff",
]
