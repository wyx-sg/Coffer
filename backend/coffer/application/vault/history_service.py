"""History, diff and restore for any vault file (spec vault-storage).

Every accepted write is a commit naming its writer, so the history of a file —
or of a folder, such as one skill's master folder — is the commits that
touched it, newest first. Restoring a version is an ordinary write of that
version's bytes through the one write path: the caller states the fingerprint
of what it last read, the result is validated like any other write, and it
lands as a new commit naming the writer and ``Coffer-Restored-From``. History
is never rewritten.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from coffer.application.vault.ports import VaultHistoryPort, VaultWriterPort
from coffer.domain.error_base import CofferError
from coffer.domain.vault.errors import VaultPathRefused
from coffer.domain.vault.findings import Finding
from coffer.domain.vault.history import (
    REMOVED,
    Commit,
    FileDiff,
    FileVersion,
    looks_like_a_version,
)
from coffer.domain.vault.layout import SECRET
from coffer.domain.vault.writers import OP_RESTORE, WRITER_USER, CommitMeta
from coffer.domain.vault.writes import Expect, check_path

MAX_PAGE = 200


class VaultVersionNotFound(CofferError):  # noqa: N818
    """No such commit, or the path did not exist in it. Maps to 404."""

    code = "VAULT_VERSION_NOT_FOUND"


@dataclass(frozen=True)
class HistoryPage:
    path: str
    versions: tuple[FileVersion, ...]
    next_cursor: str | None


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
        commits = await asyncio.to_thread(
            self._history.log, spec.rstrip("/") or ".", limit=limit + 1, skip=skip
        )
        more = len(commits) > limit
        versions = tuple(_version(c, spec) for c in commits[:limit])
        return HistoryPage(spec, versions, str(skip + limit) if more else None)

    async def changes(
        self, prefix: str = "", *, limit: int = 50, cursor: str | None = None
    ) -> tuple[tuple[Commit, ...], str | None]:
        """Recent commits under ``prefix`` (the whole vault by default)."""
        limit = max(1, min(limit, MAX_PAGE))
        skip = _skip(cursor)
        specs = (_spec(prefix).rstrip("/"),) if prefix else ()
        commits = await asyncio.to_thread(self._history.log, *specs, limit=limit + 1, skip=skip)
        more = len(commits) > limit
        return tuple(commits[:limit]), (str(skip + limit) if more else None)

    async def content(self, path: str, version: str) -> bytes:
        """``path``'s bytes as ``version`` left them."""
        path = _readable(path)
        data = await asyncio.to_thread(self._history.read, _version_id(version), path)
        if data is None:
            raise VaultVersionNotFound(f"{path} did not exist at {version}")
        return data

    async def current(self, path: str) -> bytes | None:
        """``path``'s bytes on disk now — what a caller reads before stating
        the fingerprint a restore expects (``None``: no file there)."""
        path = _readable(path)
        return await asyncio.to_thread(self._writer.read_disk, path)

    def problems(self) -> list[Finding]:
        """Every finding that keeps a hand edit out of ``HEAD``, by path."""
        return [f for _path, found in sorted(self._writer.problems().items()) for f in found]

    async def diff(self, path: str, version: str) -> FileDiff:
        """What ``version`` did to ``path``."""
        path = _readable(path)
        commit = await asyncio.to_thread(self._history.commit_of, _version_id(version))
        if commit is None:
            raise VaultVersionNotFound(f"no version {version}")
        change = next((p for p in commit.paths if p.path == path), None)
        if change is None:
            raise VaultVersionNotFound(f"{version} did not change {path}")
        text = await asyncio.to_thread(self._history.diff, commit.version, path)
        return FileDiff(path, change.status, text, change.added, change.removed)

    async def restore(
        self,
        path: str,
        version: str,
        *,
        expected_fingerprint: str | None,
        actor: str,
        writer: str = WRITER_USER,
        agent: str | None = None,
    ) -> Restored:
        """Write ``version``'s content of ``path`` back as a new commit.

        For a file, ``expected_fingerprint`` is the fingerprint of the bytes
        the caller last read (``None`` only when it read no file there). For a
        folder (``path`` ending in ``/``) every file is compared against
        ``HEAD`` instead, and files the version did not have are removed.
        """
        spec = _spec(path)
        _readable(spec.rstrip("/"))
        sha = _version_id(version)
        result = await asyncio.to_thread(
            self._restore_sync, spec, sha, expected_fingerprint, actor, writer, agent
        )
        if self._on_restored is not None:
            await self._on_restored(result, actor)
        return result

    def _restore_sync(
        self,
        spec: str,
        sha: str,
        expected: str | None,
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
            if spec.endswith("/"):
                then = self._history.tree(commit.version, spec)
                now = self._history.tree("HEAD", spec)
                for file in sorted(set(then) | set(now)):
                    data = self._history.read(commit.version, file) if file in then else None
                    if data is None:
                        txn.delete(file, Expect.HEAD)
                    elif self._writer.read_disk(file) != data:
                        txn.write(file, data, Expect.HEAD)
            else:
                data = self._history.read(commit.version, spec)
                cas: str | Expect = expected if expected is not None else Expect.ABSENT
                if data is None:
                    txn.delete(spec, cas)
                else:
                    txn.write(spec, data, cas)
            touched = tuple(txn.paths)
        return Restored(spec, txn.version, commit.version, touched)


def _spec(path: str) -> str:
    folder = path.endswith("/")
    clean = check_path(path.rstrip("/"))
    return clean + "/" if folder else clean


def _readable(path: str) -> str:
    """``path`` unless it is secret ciphertext. Rolling a secret back is
    re-entering it (ADR every-vault-write-is-a-validated-commit-naming-its-writer,
    "Credentials when not carried"), so its files are neither shown nor
    restored through history."""
    clean = check_path(path)
    if clean == SECRET or clean.startswith(f"{SECRET}/"):
        raise VaultPathRefused(f"{SECRET}/ is not read or restored through history")
    return clean


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


def _version(commit: Commit, spec: str) -> FileVersion:
    if spec.endswith("/"):
        return FileVersion(commit, spec, removed=False)
    change = next((p for p in commit.paths if p.path == spec), None)
    return FileVersion(commit, spec, removed=change is not None and change.status == REMOVED)


__all__ = ["HistoryPage", "Restored", "VaultHistoryService", "VaultVersionNotFound"]
