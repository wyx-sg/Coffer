"""The vault repository as a thin sync round uses it (implements
``application.sync.round_ports.SyncGitPort``)."""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from coffer.domain.vault.history import Commit
from coffer.domain.vault.trees import MergeResult, TreeChange
from coffer.domain.vault.writers import CommitMeta
from coffer.infrastructure.vault import git, merge, remote
from coffer.infrastructure.vault.repository import VaultRepository

SNAPSHOT_PREFIX = "coffer/pre-apply/"
SNAPSHOTS_KEPT = 10


class VaultSyncGit:
    def __init__(
        self,
        repo: VaultRepository,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
    ) -> None:
        self._repo = repo
        self._clock = clock
        self._branch = "main"

    @property
    def repo(self) -> VaultRepository:
        return self._repo

    def ensure(self) -> None:
        self._repo.ensure()

    def head(self) -> str | None:
        return self._repo.head()

    def set_remote(self, url: str) -> None:
        remote.set_remote(self._repo, url)

    def clear_remote(self) -> None:
        remote.clear_remote(self._repo)

    def set_carry_secret(self, carry: bool) -> None:
        self._repo.set_carry_secret(carry)

    def fetch(self, branch: str, token: str | None) -> str | None:
        self._branch = branch
        return remote.fetch(self._repo, branch, token).tip

    def push(self, commit: str, branch: str, token: str | None) -> None:
        remote.push(self._repo, commit, branch, token)

    def remote_tip(self, branch: str) -> str | None:
        return self._repo.resolve(remote.tracking_ref(branch))

    def merge_base(self, a: str, b: str) -> str | None:
        return merge.merge_base(self._repo, a, b)

    def is_ancestor(self, a: str, b: str) -> bool:
        return merge.is_ancestor(self._repo, a, b)

    def tree_of(self, commit: str) -> str:
        return merge.tree_of(self._repo, commit)

    def merge(self, ours: str, theirs: str, *, base: str | None = None) -> MergeResult:
        return merge.merge_trees(self._repo, ours, theirs, base=base)

    def diff(self, a: str | None, b: str) -> list[TreeChange]:
        return merge.diff_trees(self._repo, a, b)

    def renames(self, a: str, b: str) -> list[tuple[str, str]]:
        return merge.renames(self._repo, a, b)

    def files(self, commit_or_tree: str, prefix: str = "") -> dict[str, str]:
        return self._repo.tree(commit_or_tree, prefix)

    def read(self, ref: str, path: str) -> bytes | None:
        return self._repo.read(ref, path)

    def blobs(self, blobs: Sequence[str]) -> dict[str, bytes]:
        return self._repo.read_blobs(list(dict.fromkeys(blobs)))

    def hash(self, data: bytes) -> str:
        return merge.hash_blob(self._repo, data)

    def build_tree(self, base_tree: str, overrides: Mapping[str, str | None]) -> str:
        return merge.build_tree(self._repo, base_tree, overrides) if overrides else base_tree

    def commit_tree(self, tree: str, parents: tuple[str, ...], meta: CommitMeta) -> str:
        return merge.commit_tree(self._repo, tree, parents, meta)

    def checkout(self, old: str, new: str) -> None:
        merge.checkout(self._repo, old, new)

    def log(
        self, *pathspecs: str, start: str | None = None, limit: int | None = None
    ) -> list[Commit]:
        return self._repo.log(*pathspecs, start=start, limit=limit)

    def commits_between(self, since: str | None, until: str) -> list[Commit]:
        return self._repo.log(start=f"{since}..{until}" if since else until)

    def snapshot(self, commit: str) -> str:
        """Tag ``commit`` as a pre-apply snapshot; keep the ten newest."""
        stamp = self._clock().astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        name = f"{SNAPSHOT_PREFIX}{stamp}"
        existing = {n for n, _, _ in merge.tags(self._repo, SNAPSHOT_PREFIX)}
        n = 1
        while name in existing:
            name = f"{SNAPSHOT_PREFIX}{stamp}-{n}"
            n += 1
        merge.tag(self._repo, name, commit)
        for old, _, _ in merge.tags(self._repo, SNAPSHOT_PREFIX)[SNAPSHOTS_KEPT:]:
            merge.delete_tag(self._repo, old)
        return name

    def snapshots(self) -> list[tuple[str, str, int]]:
        return merge.tags(self._repo, SNAPSHOT_PREFIX)

    def merge_file(self, ours: bytes, base: bytes, theirs: bytes, labels: tuple[str, str]) -> bytes:
        """git's marked-up three-way merge of one file's contents."""
        paths: list[str] = []
        try:
            for data in (ours, base, theirs):
                fd, path = tempfile.mkstemp(prefix="coffer-merge-")
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
                paths.append(path)
            done = git.run(
                self._repo.root,
                "merge-file",
                "-p",
                "-L",
                labels[0],
                "-L",
                "base",
                "-L",
                labels[1],
                *paths,
                check=False,
            )
            return done.stdout
        finally:
            for path in paths:
                with contextlib.suppress(FileNotFoundError):
                    Path(path).unlink()


__all__ = ["SNAPSHOTS_KEPT", "SNAPSHOT_PREFIX", "VaultSyncGit"]
