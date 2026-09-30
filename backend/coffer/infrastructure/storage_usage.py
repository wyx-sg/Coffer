"""What Coffer keeps on this machine, measured, and the one part that is safe to clear.

Settings > Data (spec daemon "Report what Coffer stores and clear the
rebuildable cache") shows four kinds of data. The storage ADR
(docs/decisions/storage-is-five-classes-by-nature.md) gives each kind one
directory; until its migration lands, the kinds are measured where they live
today, and every path comes from the helper its owner already resolves it with
(so an override a test or a user set is honoured here too):

- **vault** — the sync working tree when it is a git repository (its commit
  count is the number of versions), else the knowledge and skill trees it
  would carry, with no version count;
- **local content** — chat uploads and channel media, which never sync;
- **history** — the SQLite database the records live in (with its WAL);
- **rebuildable cache** — the memory tree (fully derived from the agents' own
  memory; spec memory "Keep the memory tree derived and local") and the
  transcript summary cache. Clearing it deletes the files and leaves every
  partition's row, so the next memory update refills the folders. Authored
  memory triggers live under ``vault/memory-triggers/``, outside the tree.

Everything here blocks on the filesystem; callers run it in a thread.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
from dataclasses import dataclass

from coffer.infrastructure.agent.paths import agent_state_root
from coffer.infrastructure.channel.telegram_media import default_media_dir
from coffer.infrastructure.chat.media_store import default_chat_media_dir
from coffer.infrastructure.memory.paths import memory_root
from coffer.infrastructure.sync.paths import knowledge_root, skills_root


def coffer_home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("HOME") or "~").expanduser() / ".coffer"


def database_path() -> pathlib.Path | None:
    """The SQLite file the daemon opens (``COFFER_DB_URL`` honoured), or None for another engine."""
    url = os.environ.get("COFFER_DB_URL")
    if not url:
        # The same default the composition root opens (surfaces/http/app.py).
        return pathlib.Path.home() / ".coffer" / "coffer.db"
    prefix = url.split(":///", 1)
    if len(prefix) == 2 and prefix[0].startswith("sqlite"):
        return pathlib.Path(prefix[1])
    return None


def tree_bytes(root: pathlib.Path) -> int:
    """Total size of the regular files under ``root``; symlinks are not followed."""
    if root.is_symlink() or not root.exists():
        return 0
    if root.is_file():
        return root.stat().st_size
    total = 0
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            path = pathlib.Path(dirpath) / name
            try:
                if not path.is_symlink():
                    total += path.stat().st_size
            except OSError:
                continue
    return total


def git_version_count(repo: pathlib.Path) -> int | None:
    """Commits on ``repo``'s HEAD, or None when it is no repository or git fails."""
    if not (repo / ".git").exists():
        return None
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-list", "--count", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    try:
        return int(out.stdout.strip())
    except ValueError:
        return None


@dataclass(frozen=True)
class Measured:
    path: str
    bytes: int


@dataclass(frozen=True)
class VaultUsage(Measured):
    versions: int | None


@dataclass(frozen=True)
class LocalContentUsage:
    folder: str
    locations: list[str]
    bytes: int


@dataclass(frozen=True)
class StorageUsage:
    vault: VaultUsage
    local_content: LocalContentUsage
    history: Measured
    cache_bytes: int


def cache_roots() -> list[pathlib.Path]:
    return [memory_root(), agent_state_root()]


def measure(sync_worktree: pathlib.Path | None) -> StorageUsage:
    """Measure the four kinds; ``sync_worktree`` is the configured sync tree, if any."""
    home = coffer_home()
    if sync_worktree is not None and (sync_worktree / ".git").exists():
        vault = VaultUsage(
            path=str(sync_worktree),
            bytes=tree_bytes(sync_worktree),
            versions=git_version_count(sync_worktree),
        )
    else:
        vault = VaultUsage(
            path=str(home),
            bytes=tree_bytes(knowledge_root()) + tree_bytes(skills_root()),
            versions=None,
        )
    media = [default_chat_media_dir(), default_media_dir()]
    parents = {str(p.parent) for p in media}
    local = LocalContentUsage(
        folder=parents.pop() if len(parents) == 1 else str(home),
        locations=[str(p) for p in media],
        bytes=sum(tree_bytes(p) for p in media),
    )
    db = database_path()
    history = Measured(
        path=str(db) if db is not None else "",
        bytes=sum(tree_bytes(pathlib.Path(f"{db}{suffix}")) for suffix in ("", "-wal", "-shm"))
        if db is not None
        else 0,
    )
    return StorageUsage(
        vault=vault,
        local_content=local,
        history=history,
        cache_bytes=sum(tree_bytes(p) for p in cache_roots()),
    )


def clear_cache() -> int:
    """Empty every cache root (the roots themselves stay); return the bytes freed."""
    freed = 0
    for root in cache_roots():
        if root.is_symlink() or not root.is_dir():
            continue
        for child in root.iterdir():
            freed += tree_bytes(child)
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
    return freed


__all__ = [
    "LocalContentUsage",
    "Measured",
    "StorageUsage",
    "VaultUsage",
    "cache_roots",
    "clear_cache",
    "database_path",
    "git_version_count",
    "measure",
    "tree_bytes",
]
