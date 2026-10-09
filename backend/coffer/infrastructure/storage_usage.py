"""What Coffer keeps on this machine, measured.

Settings > Data (spec daemon "Report what Coffer stores") shows three kinds
of data, each one of the class
directories of ADR storage-is-five-classes-by-nature, resolved from ``HOME``
through ``infrastructure.vault.home`` like every other reader of them:

- **vault** — the vault repository (``vault/``), always a git repository, so
  its commit count is the number of versions (ADR
  every-vault-write-is-a-validated-commit-naming-its-writer); its size is
  the working tree and ``.git`` together;
- **local content** — channel media under ``content/``,
  which never sync;
- **history** — ``runs.db`` (with its WAL), or the database ``COFFER_DB_URL``
  names, together with the log directory (``COFFER_LOG_DIR`` honoured): logs
  are records of what happened too, pruned by the same retention pass, as are
  the skills' working files in ``skill-data/`` (logs, journals and temp files
  their scripts write; the ``skill_data`` retention policy) and the copies of
  agents' config files Coffer kept before rewriting them (``config-backups/``;
  the ``config_backups`` retention policy).

Everything here blocks on the filesystem; callers run it in a thread.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
from dataclasses import dataclass

from coffer.infrastructure.channel.media_root import default_media_dir
from coffer.infrastructure.logging.files import log_dir
from coffer.infrastructure.vault.home import (
    config_backups_dir,
    content_root,
    runs_db_path,
    skill_data_dir,
    vault_root,
)


def database_path() -> pathlib.Path | None:
    """The SQLite file the daemon opens (``COFFER_DB_URL`` honoured), or None for another engine."""
    url = os.environ.get("COFFER_DB_URL")
    if not url:
        # The same default the composition root opens (surfaces/http/app.py).
        return runs_db_path()
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


def measure() -> StorageUsage:
    """Measure the three kinds."""
    vault_dir = vault_root()
    vault = VaultUsage(
        path=str(vault_dir),
        bytes=tree_bytes(vault_dir),
        versions=git_version_count(vault_dir),
    )
    media = [default_media_dir()]
    parents = {str(p.parent) for p in media}
    local = LocalContentUsage(
        folder=parents.pop() if len(parents) == 1 else str(content_root()),
        locations=[str(p) for p in media],
        bytes=sum(tree_bytes(p) for p in media),
    )
    db = database_path()
    db_bytes = (
        sum(tree_bytes(pathlib.Path(f"{db}{suffix}")) for suffix in ("", "-wal", "-shm"))
        if db is not None
        else 0
    )
    history = Measured(
        path=str(db) if db is not None else "",
        bytes=db_bytes
        + tree_bytes(log_dir())
        + tree_bytes(skill_data_dir())
        + tree_bytes(config_backups_dir()),
    )
    return StorageUsage(
        vault=vault,
        local_content=local,
        history=history,
    )


__all__ = [
    "LocalContentUsage",
    "Measured",
    "StorageUsage",
    "VaultUsage",
    "database_path",
    "git_version_count",
    "measure",
    "tree_bytes",
]
