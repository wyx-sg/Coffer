"""An in-memory vault repository and remote for the round engine's unit tests.

It implements the part of :class:`~coffer.application.sync.round_ports.SyncGitPort`
a round walks through, over plain dictionaries: a tree is ``{path: blob}``, a
commit is a tree and its parents, and a merge is git's three-way rule path by
path (one side's change wins over an unchanged side; two different changes
conflict). It records every call that would change the vault or the remote —
snapshot, checkout, push — so a test can assert that a stopped or held round
made none of them.

It is a model of git, not git: no rename detection (``renames`` pairs nothing),
no content merge inside a file, no history walk beyond the parent graph.
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from coffer.domain.sync.stops import ConflictFile, Stop
from coffer.domain.vault.history import Commit
from coffer.domain.vault.trees import ConflictEntry, MergeResult, TreeChange
from coffer.domain.vault.writers import CommitMeta
from coffer.domain.vault.writes import CommitResult

Tree = dict[str, str]


def _digest(kind: str, payload: str) -> str:
    return hashlib.sha1(f"{kind}\0{payload}".encode()).hexdigest()


class FakeGit:
    def __init__(self) -> None:
        self.blobs_by_id: dict[str, bytes] = {}
        self.trees: dict[str, Tree] = {}
        self.parents: dict[str, tuple[str, ...]] = {}
        self.tree_of_commit: dict[str, str] = {}
        self.local: str | None = None
        self.remote: str | None = None
        #: What changed the vault or the remote, in order.
        self.snapshotted: list[str] = []
        self.checkouts: list[tuple[str, str]] = []
        self.pushes: list[str] = []

    # --- building history ------------------------------------------------------

    def put_blob(self, data: bytes) -> str:
        blob = _digest("blob", data.hex())
        self.blobs_by_id[blob] = data
        return blob

    def put_tree(self, files: Mapping[str, str]) -> str:
        tree = _digest("tree", repr(sorted(files.items())))
        self.trees[tree] = dict(files)
        return tree

    def commit(self, files: Mapping[str, bytes], parents: tuple[str, ...] = ()) -> str:
        tree = self.put_tree({p: self.put_blob(d) for p, d in files.items()})
        return self._commit(tree, parents)

    def _commit(self, tree: str, parents: tuple[str, ...]) -> str:
        commit = _digest("commit", f"{tree}{parents}{len(self.parents)}")
        self.parents[commit] = parents
        self.tree_of_commit[commit] = tree
        return commit

    def contents(self, ref: str) -> dict[str, bytes]:
        return {p: self.blobs_by_id[b] for p, b in self._tree(ref).items()}

    def _tree(self, ref: str | None) -> Tree:
        if ref is None:
            return {}
        if ref in self.tree_of_commit:
            return self.trees[self.tree_of_commit[ref]]
        return self.trees[ref]

    def _ancestors(self, commit: str) -> set[str]:
        seen: set[str] = set()
        todo = [commit]
        while todo:
            c = todo.pop()
            if c not in seen:
                seen.add(c)
                todo.extend(self.parents[c])
        return seen

    # --- SyncGitPort -----------------------------------------------------------

    def ensure(self) -> None:
        pass

    def head(self) -> str | None:
        return self.local

    def set_remote(self, url: str, username: str | None = None) -> None:
        pass

    def clear_remote(self) -> None:
        pass

    def set_carry_secret(self, carry: bool) -> None:
        pass

    def fetch(self, branch: str, token: str | None) -> str | None:
        return self.remote

    def push(self, commit: str, branch: str, token: str | None) -> None:
        self.pushes.append(commit)
        self.remote = commit

    def remote_tip(self, branch: str) -> str | None:
        return self.remote

    def merge_base(self, a: str, b: str) -> str | None:
        common = self._ancestors(a) & self._ancestors(b)
        # The common ancestor no other common ancestor descends from.
        best = [c for c in common if not any(c in self._ancestors(o) - {o} for o in common)]
        return best[0] if best else None

    def is_ancestor(self, a: str, b: str) -> bool:
        return a in self._ancestors(b)

    def tree_of(self, commit: str) -> str:
        return self.tree_of_commit[commit]

    def merge(self, ours: str, theirs: str, *, base: str | None = None) -> MergeResult:
        base = base if base is not None else self.merge_base(ours, theirs)
        o, t, b = self._tree(ours), self._tree(theirs), self._tree(base)
        merged: Tree = {}
        conflicts: list[ConflictEntry] = []
        for path in sorted(set(o) | set(t) | set(b)):
            mine, other, was = o.get(path), t.get(path), b.get(path)
            if mine == other or other == was:
                pick = mine
            elif mine == was:
                pick = other
            else:
                conflicts.append(ConflictEntry(path, was, mine, other))
                pick = mine  # git leaves a marked-up file; this side stands in for it
            if pick is not None:
                merged[path] = pick
        return MergeResult(self.put_tree(merged), tuple(conflicts))

    def diff(self, a: str | None, b: str) -> list[TreeChange]:
        old, new = self._tree(a), self._tree(b)
        out: list[TreeChange] = []
        for path in sorted(set(old) | set(new)):
            was, now = old.get(path), new.get(path)
            if was == now:
                continue
            status = "A" if was is None else "D" if now is None else "M"
            out.append(TreeChange(path, status, was, now))
        return out

    def renames(self, a: str, b: str) -> list[tuple[str, str]]:
        return []

    def files(self, commit_or_tree: str, prefix: str = "") -> dict[str, str]:
        prefix = prefix.rstrip("/")
        return {
            p: blob
            for p, blob in self._tree(commit_or_tree).items()
            if not prefix or p == prefix or p.startswith(prefix + "/")
        }

    def read(self, ref: str, path: str) -> bytes | None:
        blob = self._tree(ref).get(path)
        return self.blobs_by_id[blob] if blob else None

    def blobs(self, blobs: Sequence[str]) -> dict[str, bytes]:
        return {b: self.blobs_by_id[b] for b in blobs if b in self.blobs_by_id}

    def hash(self, data: bytes) -> str:
        return self.put_blob(data)

    def build_tree(self, base_tree: str, overrides: Mapping[str, str | None]) -> str:
        files = dict(self._tree(base_tree))
        for path, blob in overrides.items():
            if blob is None:
                files.pop(path, None)
            else:
                files[path] = blob
        return self.put_tree(files)

    def commit_tree(self, tree: str, parents: tuple[str, ...], meta: CommitMeta) -> str:
        return self._commit(tree, parents)

    def checkout(self, old: str, new: str) -> None:
        assert old == self.local, "checked out over a vault that moved"
        self.checkouts.append((old, new))
        self.local = new

    def log(
        self, *pathspecs: str, start: str | None = None, limit: int | None = None
    ) -> list[Commit]:
        return []

    def commits_between(self, since: str | None, until: str) -> list[Commit]:
        return []

    def snapshot(self, commit: str) -> str:
        self.snapshotted.append(commit)
        return f"snapshot-{len(self.snapshotted)}"

    def snapshots(self) -> list[tuple[str, str, int]]:
        return []

    def merge_file(self, ours: bytes, base: bytes, theirs: bytes, labels: tuple[str, str]) -> bytes:
        return ours


@dataclass
class FakeState:
    """``local/sync/round.json`` in memory."""

    current: Stop | None = None
    choices: tuple[ConflictFile, ...] = ()
    pair: tuple[str, str] | None = None
    is_joined: bool = True

    def stop(self) -> Stop | None:
        return self.current

    def set_stop(self, stop: Stop | None) -> None:
        self.current = stop

    def join_choices(self) -> tuple[ConflictFile, ...]:
        return self.choices

    def set_join_choices(self, choices: Sequence[ConflictFile]) -> None:
        self.choices = tuple(choices)

    def confirmed(self) -> tuple[str, str] | None:
        return self.pair

    def set_confirmed(self, pair: tuple[str, str] | None) -> None:
        self.pair = pair

    def joined(self) -> bool:
        return self.is_joined

    def set_joined(self, joined: bool) -> None:
        self.is_joined = joined


@dataclass
class FakeWriter:
    """The vault writer, committing straight onto the fake repository's head."""

    git: FakeGit
    notified: list[CommitResult] = field(default_factory=list)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    @property
    def lock(self) -> Any:
        return self._lock

    def settle(self, paths: Sequence[str] | None = None, *, meta: CommitMeta | None = None) -> None:
        return None

    def write_file(
        self, path: str, data: bytes, *, meta: CommitMeta, expected: Any = None
    ) -> str | None:
        head = self.git.local
        assert head is not None
        tree = self.git.build_tree(self.git.tree_of(head), {path: self.git.put_blob(data)})
        self.git.local = self.git.commit_tree(tree, (head,), meta)
        return self.git.local

    def notify(self, result: CommitResult) -> None:
        self.notified.append(result)


class FakeMachine:
    def __init__(self, machine_id: str = "mac") -> None:
        self.id = machine_id

    def machine_id(self) -> str:
        return self.id

    def label(self) -> str:
        return self.id

    def descriptor_path(self) -> str:
        return f"machines/{self.id}.json"

    def descriptor(self, *, last_round_at: str | None, last_commit: str | None) -> bytes:
        return f'{{"machine_id": "{self.id}", "last_converged_commit": "{last_commit}"}}\n'.encode()

    def labels(self, files: Mapping[str, bytes]) -> dict[str, str]:
        return {}


__all__ = ["FakeGit", "FakeMachine", "FakeState", "FakeWriter"]
