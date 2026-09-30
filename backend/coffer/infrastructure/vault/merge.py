"""Merging vault commits without touching the working tree
(ADR sync-applies-clean-merges-and-stops-on-any-conflict).

A round never merges *in* the vault. ``git merge-tree --write-tree`` computes
the merge of two commits — against their merge base, or against a base the
caller names — into a tree object in the repository's object store and reports
every conflicting path; nothing in the working tree, the index or ``HEAD``
changes until the round decides to check the result out. Trees for a
resolution (a file taken from one side, a credential settled by its
encryption time) are built in a throwaway index, never the vault's own.

The checkout is a compare-and-swap on the whole tree: ``read-tree -m -u
<old> <new>`` verifies that every path it will change is unmodified relative
to ``<old>`` before writing any file, and ``update-ref`` moves the branch only
if it still points at ``<old>``.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path

from coffer.domain.vault.errors import VaultFileStale
from coffer.domain.vault.trees import ConflictEntry, MergeResult, TreeChange
from coffer.domain.vault.writers import CommitMeta, message
from coffer.infrastructure.vault import git
from coffer.infrastructure.vault.repository import VaultRepository

#: ``merge-tree --write-tree`` needs git 2.38; ``--merge-base`` needs 2.40.
MIN_GIT = (2, 40)


def git_version(repo: VaultRepository) -> tuple[int, int]:
    done = git.run(repo.root, "--version", check=False)
    words = git.text(done).split()
    try:
        major, minor = words[2].split(".")[:2]
        return int(major), int(minor)
    except (IndexError, ValueError):
        return (0, 0)


def merge_base(repo: VaultRepository, a: str, b: str) -> str | None:
    done = git.run(repo.root, "merge-base", a, b, check=False)
    sha = git.text(done).strip()
    return sha if done.returncode == 0 and sha else None


def is_ancestor(repo: VaultRepository, a: str, b: str) -> bool:
    return git.run(repo.root, "merge-base", "--is-ancestor", a, b, check=False).returncode == 0


def tree_of(repo: VaultRepository, commit: str) -> str:
    return git.text(git.run(repo.root, "rev-parse", f"{commit}^{{tree}}")).strip()


def merge_trees(
    repo: VaultRepository, ours: str, theirs: str, *, base: str | None = None
) -> MergeResult:
    """The merge of ``ours`` and ``theirs`` as a tree, with every conflict.

    ``base`` names the merge base explicitly (a returning machine's base
    recovered from its descriptor); otherwise git finds it.
    """
    args = ["merge-tree", "--write-tree", "-z", "--no-messages"]
    if base is not None:
        args.append(f"--merge-base={base}")
    args += [ours, theirs]
    done = git.run(repo.root, *args, check=False)
    if done.returncode not in (0, 1):
        raise git.VaultGitError(git.failure_message(args, done))
    raw = done.stdout.decode("utf-8", "replace")
    tree, _, rest = raw.partition("\0")
    stages: dict[str, dict[int, str]] = {}
    if done.returncode == 1:
        for entry in rest.split("\0"):
            if not entry:
                break  # the empty entry ends the conflicted-file list
            meta, _, path = entry.partition("\t")
            parts = meta.split()
            if len(parts) == 3:
                stages.setdefault(path, {})[int(parts[2])] = parts[1]
    conflicts = tuple(
        ConflictEntry(path, s.get(1), s.get(2), s.get(3)) for path, s in sorted(stages.items())
    )
    return MergeResult(tree.strip(), conflicts)


def diff_trees(repo: VaultRepository, a: str | None, b: str) -> list[TreeChange]:
    """Every path that differs from ``a`` to ``b`` (renames off). ``a=None``
    compares against the empty tree."""
    old = a or _empty_tree(repo)
    done = git.run(
        repo.root, "diff-tree", "-r", "-z", "--no-renames", "--raw", "--abbrev=40", old, b
    )
    out: list[TreeChange] = []
    fields_ = done.stdout.decode("utf-8", "replace").split("\0")
    i = 0
    while i < len(fields_) - 1:
        meta = fields_[i]
        if not meta.startswith(":"):
            i += 1
            continue
        path = fields_[i + 1]
        parts = meta[1:].split()
        old_blob, new_blob, status = parts[2], parts[3], parts[4][:1]
        zero = "0" * 40
        out.append(
            TreeChange(
                path,
                status,
                None if old_blob == zero else old_blob,
                None if new_blob == zero else new_blob,
            )
        )
        i += 2
    return out


def renames(repo: VaultRepository, a: str, b: str) -> list[tuple[str, str]]:
    """git's own rename pairs from ``a`` to ``b`` (for the breaker only)."""
    done = git.run(
        repo.root, "diff-tree", "-r", "-z", "-M", "--diff-filter=R", "--raw", a, b, check=False
    )
    parts = done.stdout.decode("utf-8", "replace").split("\0")
    out: list[tuple[str, str]] = []
    i = 0
    while i < len(parts) - 2:
        if parts[i].startswith(":") and parts[i].split()[-1].startswith("R"):
            out.append((parts[i + 1], parts[i + 2]))
            i += 3
        else:
            i += 1
    return out


def ls_tree(repo: VaultRepository, tree: str, prefix: str = "") -> dict[str, str]:
    return repo.tree(tree, prefix)


def hash_blob(repo: VaultRepository, data: bytes) -> str:
    """Write ``data`` as a blob into the object store; answer its id."""
    return git.text(git.run(repo.root, "hash-object", "-w", "--stdin", stdin=data)).strip()


def build_tree(repo: VaultRepository, base_tree: str, overrides: Mapping[str, str | None]) -> str:
    """``base_tree`` with each path in ``overrides`` set to a blob (or removed
    for ``None``), built in a throwaway index."""
    fd, index = tempfile.mkstemp(prefix="coffer-index-")
    os.close(fd)
    os.unlink(index)
    env = {"GIT_INDEX_FILE": index}
    try:
        git.run(repo.root, "read-tree", base_tree, extra_env=env)
        removals = [p for p, b in overrides.items() if b is None]
        if removals:
            git.run(
                repo.root,
                "update-index",
                "--force-remove",
                "-z",
                "--stdin",
                stdin=("\0".join(removals) + "\0").encode(),
                extra_env=env,
            )
        adds = "".join(f"100644 {b}\t{p}\0" for p, b in overrides.items() if b is not None)
        if adds:
            git.run(
                repo.root, "update-index", "-z", "--index-info", stdin=adds.encode(), extra_env=env
            )
        return git.text(git.run(repo.root, "write-tree", extra_env=env)).strip()
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(index)


def commit_tree(
    repo: VaultRepository, tree: str, parents: tuple[str, ...], meta: CommitMeta
) -> str:
    args = ["commit-tree", tree]
    for parent in parents:
        args += ["-p", parent]
    done = git.run(repo.root, *args, stdin=message(meta).encode(), writer=meta.writer)
    return git.text(done).strip()


def checkout(repo: VaultRepository, old: str, new: str, *, branch: str = "main") -> None:
    """Move the working tree and ``branch`` from ``old`` to ``new``.

    Refuses — changing nothing — when a path that differs between the two has
    an uncommitted edit on disk, or when ``branch`` no longer points at
    ``old``; the round then waits and names the path.
    """
    head = repo.head()
    if head != old:
        raise VaultFileStale("HEAD", "the vault moved while the round was running")
    done = git.run(repo.root, "read-tree", "-m", "-u", old, new, check=False)
    if done.returncode != 0:
        detail = git.text(done) + done.stderr.decode("utf-8", "replace")
        raise VaultFileStale(
            _first_path(detail) or "vault", f"an edit on disk is in the way: {detail.strip()}"
        )
    git.run(repo.root, "update-ref", f"refs/heads/{branch}", new, old)


def _first_path(detail: str) -> str | None:
    for line in detail.splitlines():
        line = line.strip()
        if line and not line.startswith(("error", "Please", "Aborting", "fatal")):
            return line
    return None


def _empty_tree(repo: VaultRepository) -> str:
    return git.text(git.run(repo.root, "hash-object", "-t", "tree", "--stdin", stdin=b"")).strip()


def tag(repo: VaultRepository, name: str, commit: str) -> None:
    git.run(repo.root, "tag", "-f", name, commit)


def tags(repo: VaultRepository, prefix: str) -> list[tuple[str, str, int]]:
    """``(name, commit, unix time)`` of each tag under ``prefix``, newest first."""
    done = git.run(
        repo.root,
        "for-each-ref",
        "--sort=-creatordate",
        "--format=%(refname:short)%09%(objectname)%09%(creatordate:unix)",
        f"refs/tags/{prefix}",
        check=False,
    )
    out: list[tuple[str, str, int]] = []
    for line in git.text(done).splitlines():
        name, _, rest = line.partition("\t")
        sha, _, when = rest.partition("\t")
        if name and sha:
            out.append((name, sha, int(when or 0)))
    return out


def delete_tag(repo: VaultRepository, name: str) -> None:
    git.run(repo.root, "tag", "-d", name, check=False)


def path_exists(root: Path, path: str) -> bool:
    return (root / path).exists()


__all__ = [
    "MIN_GIT",
    "ConflictEntry",
    "MergeResult",
    "TreeChange",
    "build_tree",
    "checkout",
    "commit_tree",
    "delete_tag",
    "diff_trees",
    "git_version",
    "hash_blob",
    "is_ancestor",
    "ls_tree",
    "merge_base",
    "merge_trees",
    "renames",
    "tag",
    "tags",
    "tree_of",
]
