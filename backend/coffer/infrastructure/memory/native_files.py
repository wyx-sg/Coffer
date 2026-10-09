"""Writing into an agent's own memory directory, carefully (spec memory
"Leave every memory an agent wrote untouched").

Every write is atomic (a sibling temp file renamed into place), and before
Coffer changes a file it did not create wholesale — Claude Code's
``MEMORY.md`` — a copy goes to ``~/.coffer/config-backups/`` in the same
layout the agent config store uses (``<name>-<12 hex of the path>/<name>
.coffer-backup-<UTC time>``), so the ``config_backups`` retention policy bounds
it with every other backup of an agent's file.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import shutil
from datetime import UTC, datetime

from coffer.infrastructure.vault.home import config_backups_dir

_STAMP_FORMAT = "%Y%m%dT%H%M%S%fZ"
BACKUP_MARK = ".coffer-backup-"


def digest(path: str | pathlib.Path) -> str | None:
    """The content digest of ``path``, or ``None`` when it is not a file."""
    try:
        return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return None
    except OSError:
        return None


def read(path: pathlib.Path) -> str | None:
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.coffer-tmp")
    tmp.write_bytes(text.encode("utf-8"))
    os.replace(tmp, path)


def remove(path: pathlib.Path) -> bool:
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


def backup(path: pathlib.Path) -> pathlib.Path | None:
    """Copy ``path`` into its backup folder; ``None`` when there is nothing."""
    if not path.is_file():
        return None
    absolute = os.path.abspath(path)
    key = hashlib.sha256(absolute.encode()).hexdigest()[:12]
    folder = config_backups_dir() / f"{os.path.basename(absolute)}-{key}"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(tz=UTC).strftime(_STAMP_FORMAT)
    dest = folder / f"{path.name}{BACKUP_MARK}{stamp}"
    n = 0
    while dest.exists():
        n += 1
        dest = folder / f"{path.name}{BACKUP_MARK}{stamp}-{n}"
    shutil.copyfile(path, dest)
    dest.chmod(0o600)
    return dest


__all__ = ["BACKUP_MARK", "backup", "digest", "read", "remove", "write"]
