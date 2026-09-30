"""The knowledge tree's own history becomes the vault's, and its curation
stamps become ``local/curation.json`` (plan q9 §3 step 5; D14).

**History.** The previous layout kept knowledge's history in a repository of
its own (``<knowledge root>/.git``). Its commits are replayed into the vault
repository one for one — each commit's message, author and committer with
their dates kept, its tree nested under ``knowledge/`` beside what the
vault's first commit holds, its parents mapped — so ``coffer vault history``
of a knowledge document reads back to its first version. Nothing is
rewritten in the old repository: its objects are fetched, and the directory
is then renamed into the backup set (a rollback renames it back).

**Stamps.** Each document carried ``coffer_curated_at``, and curation judged
an edit by the file's mtime against it. This build compares blobs instead, so
the key is stripped (one render, the knowledge layer's own) and a document
whose mtime was not past its stamp — one curation had settled — is recorded
as settled with its stripped bytes, so it is not curated again. The stamped
original is renamed into the backup set; a rollback puts it back when the
stripped file has not changed since.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from coffer.domain.vault.content_ids import blob_id
from coffer.infrastructure.knowledge import curation_state
from coffer.infrastructure.knowledge.catalogue import is_markdown
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter
from coffer.infrastructure.knowledge.fs import decode, render
from coffer.infrastructure.vault import git
from coffer.infrastructure.vault.atomic import atomic_write
from coffer.infrastructure.vault.migration.places import STAMPED_BACKUP, at
from coffer.infrastructure.vault.migration.record import Stamped
from coffer.infrastructure.vault.repository import VaultRepository

#: The key the previous build wrote into every document curation had seen.
CURATED_AT_KEY = "coffer_curated_at"
_IMPORT_REF = "refs/coffer/migration/knowledge"
_PERSON = re.compile(rb"^(author|committer) (.*) <(.*)> (\d+ [+-]\d{4})$")


@dataclass(frozen=True)
class _Commit:
    sha: str
    parents: tuple[str, ...]


def fetch_history(repo: VaultRepository, old_git: Path) -> bool:
    """Copy the old knowledge repository's objects into the vault repository
    (under a temporary ref); ``False`` when it has no commit to fold."""
    if not old_git.is_dir():
        return False
    done = git.run(
        repo.root, "fetch", "--no-tags", "-q", str(old_git), f"+HEAD:{_IMPORT_REF}", check=False
    )
    return done.returncode == 0 and repo.resolve(_IMPORT_REF) is not None


def _commits(repo: VaultRepository) -> list[_Commit]:
    out = git.text(repo.run("rev-list", "--reverse", "--topo-order", "--parents", _IMPORT_REF))  # type: ignore[arg-type]
    commits: list[_Commit] = []
    for line in out.splitlines():
        sha, *parents = line.split()
        commits.append(_Commit(sha, tuple(parents)))
    return commits


def _identity(raw: bytes) -> tuple[dict[str, str], bytes]:
    """The author/committer environment and the message of a raw commit."""
    head, _sep, body = raw.partition(b"\n\n")
    env: dict[str, str] = {}
    for line in head.split(b"\n"):
        m = _PERSON.match(line)
        if m is None:
            continue
        role = m.group(1).decode().upper()
        env[f"GIT_{role}_NAME"] = m.group(2).decode("utf-8", "replace")
        env[f"GIT_{role}_EMAIL"] = m.group(3).decode("utf-8", "replace")
        env[f"GIT_{role}_DATE"] = m.group(4).decode()
    return env, body


def fold_history(repo: VaultRepository) -> int:
    """Replay the fetched knowledge history on top of the vault's first
    commit; ``HEAD`` and the index end at the last replayed commit."""
    root = repo.root
    base = repo.head()
    assert base is not None, "the vault has its first commit before the fold"
    listing = git.run(root, "ls-tree", "-z", base).stdout
    entries = [e for e in listing.split(b"\0") if e and not e.endswith(b"\tknowledge")]
    mapped: dict[str, str] = {}
    last = base
    for commit in _commits(repo):
        tree = git.text(git.run(root, "rev-parse", f"{commit.sha}^{{tree}}")).strip()
        nested = b"\0".join([*entries, f"040000 tree {tree}\tknowledge".encode()]) + b"\0"
        new_tree = git.text(git.run(root, "mktree", "-z", stdin=nested)).strip()
        env, message = _identity(git.run(root, "cat-file", "commit", commit.sha).stdout)
        parents = [mapped[p] for p in commit.parents if p in mapped] or [base]
        args = ["commit-tree", new_tree]
        for parent in parents:
            args += ["-p", parent]
        made = git.run(root, *args, stdin=message, extra_env=env)
        mapped[commit.sha] = last = git.text(made).strip()
    if last != base:
        git.run(root, "update-ref", "HEAD", last)
        git.run(root, "read-tree", "HEAD")
    git.run(root, "update-ref", "-d", _IMPORT_REF, check=False)
    return len(mapped)


def _documents(knowledge: Path) -> list[Path]:
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(knowledge):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        out.extend(Path(dirpath) / n for n in sorted(filenames) if is_markdown(n))
    return out


def _parse(stamp: str) -> float:
    try:
        return datetime.fromisoformat(stamp).timestamp()
    except ValueError:
        return 0.0


def strip_stamps(home: Path, knowledge: Path) -> list[Stamped]:
    """Strip ``coffer_curated_at`` from every document under ``knowledge``
    (the moved root), keeping each original in the backup set, and seed
    ``local/curation.json`` for those curation had settled."""
    stamped: list[Stamped] = []
    backup = at(home, STAMPED_BACKUP)
    for path in _documents(knowledge):
        raw = path.read_bytes()
        fm, body = split_frontmatter(decode(raw))
        if CURATED_AT_KEY not in fm:
            continue
        stamp = str(fm.pop(CURATED_AT_KEY) or "")
        settled = bool(stamp) and _parse(stamp) >= path.stat().st_mtime
        stripped = render(fm, body).encode("utf-8")
        relpath = path.relative_to(knowledge).as_posix()
        keep = backup / relpath
        keep.parent.mkdir(parents=True, exist_ok=True)
        mode = path.stat().st_mode & 0o777
        path.rename(keep)
        atomic_write(path, stripped, mode=mode)
        if settled:
            curation_state.record(relpath, stripped, when=stamp)
        stamped.append(Stamped(path=relpath, blob=blob_id(stripped)))
    return stamped


def restore_stamps(home: Path, knowledge: Path, stamped: list[Stamped]) -> list[str]:
    """Put each stamped original back where the stripped file is unchanged;
    answer the documents a person changed since (left as they are)."""
    kept: list[str] = []
    backup = at(home, STAMPED_BACKUP)
    for item in stamped:
        original, current = backup / item.path, knowledge / item.path
        if not original.is_file():
            continue
        if current.is_file() and blob_id(current.read_bytes()) != item.blob:
            kept.append(
                f"{current} was edited after the upgrade; its stamped original is {original}"
            )
            continue
        original.rename(current)
    return kept


__all__ = ["CURATED_AT_KEY", "fetch_history", "fold_history", "restore_stamps", "strip_stamps"]
