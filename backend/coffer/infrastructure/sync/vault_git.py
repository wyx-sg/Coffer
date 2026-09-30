"""The vault repository as a thin sync round uses it (implements
``application.sync.round_ports.SyncGitPort``)."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from coffer.domain.vault.history import Commit
from coffer.domain.vault.layout import MANIFEST
from coffer.domain.vault.remote_errors import RemoteFailed
from coffer.domain.vault.trees import MergeResult, TreeChange
from coffer.domain.vault.writers import CommitMeta
from coffer.infrastructure.vault import git, merge, remote
from coffer.infrastructure.vault.repository import VaultRepository

SNAPSHOT_PREFIX = "coffer/pre-apply/"
_PROBE_REF = "refs/coffer/probe"
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
        self._username: str | None = None

    @property
    def repo(self) -> VaultRepository:
        return self._repo

    def ensure(self) -> None:
        self._repo.ensure()

    def head(self) -> str | None:
        return self._repo.head()

    def set_remote(self, url: str, username: str | None = None) -> None:
        remote.set_remote(self._repo, url)
        self._username = username

    def clear_remote(self) -> None:
        remote.clear_remote(self._repo)

    def set_carry_secret(self, carry: bool) -> None:
        self._repo.set_carry_secret(carry)

    def fetch(self, branch: str, token: str | None) -> str | None:
        self._branch = branch
        return remote.fetch(self._repo, branch, token, self._username).tip

    def push(self, commit: str, branch: str, token: str | None) -> None:
        remote.push(self._repo, commit, branch, token, self._username)

    def probe(
        self, url: str, branch: str, token: str | None, username: str | None = None
    ) -> str | None:
        """The tip of ``branch`` at ``url`` without fetching (``None``: empty)."""
        self._repo.ensure()
        return remote.probe(self._repo, url, branch, token, username)

    def probe_layout(
        self, url: str, branch: str, token: str | None, username: str | None = None
    ) -> int | None:
        """The layout the vault at ``url`` carries, or ``None`` when what is
        there is not a Coffer vault. Fetched into a scratch ref that is
        deleted again; the objects stay, which a later join fetches anyway."""
        self._repo.ensure()
        args = ("fetch", "--no-tags", "--quiet", url, f"+refs/heads/{branch}:{_PROBE_REF}")
        done = git.run(
            self._repo.root,
            *args,
            token=token,
            username=username,
            timeout=git.NETWORK_TIMEOUT_S,
            check=False,
        )
        if done.returncode != 0:
            detail = git.failure_message(args, done, token)
            raise RemoteFailed(remote.classify(detail), detail)
        try:
            raw = self._repo.read(_PROBE_REF, MANIFEST)
        finally:
            git.run(self._repo.root, "update-ref", "-d", _PROBE_REF, check=False)
        if raw is None:
            return None
        try:
            value = json.loads(raw.decode("utf-8")).get("schema_version")
        except (ValueError, AttributeError):
            return None
        return value if isinstance(value, int) else None

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
