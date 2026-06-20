"""Vault-level backup / restore of Coffer's on-disk state.

The vault root is ``~/.coffer/``. Inside it, the *system of record* is a set of
markdown file trees — the knowledge bases (``knowledge/``), the memory store
(``memory/``) and the managed skills (``skills/``). ``coffer.db`` is the
*rebuildable index* over those trees, not the source of truth.

A faithful backup therefore captures the file trees AND the db, not the db
alone. ``coffer.db`` is included so a restore is instant (no reindex needed),
but it could in principle be rebuilt from the trees.

Master-key policy
-----------------
The credential master key (``master.key``, the Fernet key) is the only secret
material that lives outside the db; the credential ciphertext in ``coffer.db``
is unreadable without it. A backup is meant to be safe to copy off-machine, so
bundling the master key next to the ciphertext it unlocks would defeat the
encryption. The key is therefore **excluded by default**. Pass
``include_master_key=True`` to bundle it — only into storage you trust as much
as the live key. Without the key, a restored vault works for everything except
*reading* previously-stored credentials, which must be re-entered (or the same
key re-placed at ``~/.coffer/master.key``).
"""

from __future__ import annotations

import contextlib
import os
import shutil
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# Directory subtrees under the vault root that hold the system-of-record files.
_TREE_NAMES: tuple[str, ...] = ("knowledge", "memory", "skills")
_DB_NAME = "coffer.db"
_MASTER_KEY_NAME = "master.key"


def vault_root() -> Path:
    """``~/.coffer/`` — the common parent of the db, file trees and master key."""
    return Path(os.environ.get("HOME", "~")).expanduser() / ".coffer"


class BackupError(Exception):
    """A backup or restore precondition was violated (caller turns into exit)."""


@dataclass
class BackupManifest:
    """What a backup / restore actually moved, for human-readable reporting."""

    db: bool = False
    trees: list[str] = field(default_factory=list)
    master_key: bool = False


def create_backup(dest: Path, *, include_master_key: bool = False) -> BackupManifest:
    """Write the live vault (db + file trees) into a ``.tar.gz`` archive at ``dest``.

    ``dest`` is the output file path (e.g. ``~/backups/coffer-20260620.tar.gz``).
    The archive is written atomically: a temp file is created in the same
    directory as ``dest``, fully populated, then renamed onto ``dest``.

    Raises :class:`BackupError` when there is no vault to back up (neither db
    nor any file tree exists). The master key is only included when
    ``include_master_key`` is True.

    Archive member paths are relative to the vault root, so extraction
    reconstructs the original layout:
      - ``coffer.db``
      - ``knowledge/…``, ``memory/…``, ``skills/…`` (whichever exist)
      - ``master.key`` (only if ``include_master_key=True``)
    """
    root = vault_root()
    has_db = (root / _DB_NAME).exists()
    has_tree = any((root / name).is_dir() for name in _TREE_NAMES)
    if not has_db and not has_tree:
        raise BackupError(f"no vault found at {root} — nothing to back up")

    manifest = BackupManifest()
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Write atomically: tar to a temp file, then os.replace onto dest.
    fd, tmp_path = tempfile.mkstemp(dir=dest.parent, prefix=".coffer-backup-", suffix=".tar.gz.tmp")
    try:
        os.close(fd)
        with tarfile.open(tmp_path, "w:gz") as tar:
            # Always add coffer.db (existence already confirmed above via has_db,
            # but check once more to be explicit for the manifest).
            db_path = root / _DB_NAME
            if db_path.exists():
                tar.add(db_path, arcname=_DB_NAME)
                manifest.db = True

            # Add each existing tree using its name as the arcname prefix so
            # members are stored as e.g. ``knowledge/handbook/docs/welcome.md``.
            for name in _TREE_NAMES:
                tree = root / name
                if tree.is_dir():
                    tar.add(tree, arcname=name)
                    manifest.trees.append(name)

            # Master key is opt-in only.
            if include_master_key:
                key_path = root / _MASTER_KEY_NAME
                if key_path.exists():
                    tar.add(key_path, arcname=_MASTER_KEY_NAME)
                    manifest.master_key = True

        os.replace(tmp_path, dest)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise

    return manifest


def verify_backup(src: Path) -> None:
    """Reject a source path that is not a recognisable vault backup.

    Requires ``src`` to be a readable ``.tar.gz`` containing ``coffer.db``
    (the one component every backup carries). Raises :class:`BackupError`
    otherwise — checked before any clobbering.
    """
    if not src.is_file():
        raise BackupError(f"backup source {src} is not a file")
    try:
        with tarfile.open(src, "r:gz") as tar:
            names = tar.getnames()
    except tarfile.TarError as exc:
        raise BackupError(f"invalid backup: {src} is not a valid tar.gz archive ({exc})") from exc
    if _DB_NAME not in names:
        raise BackupError(f"invalid backup: {src} has no {_DB_NAME}")


def vault_is_populated() -> bool:
    """True when the live vault already holds a db or any file tree."""
    root = vault_root()
    if (root / _DB_NAME).exists():
        return True
    return any((root / name).is_dir() for name in _TREE_NAMES)


def _remove(path: Path) -> None:
    """Delete a file or directory, tolerating absence."""
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()


def restore_backup(src: Path) -> BackupManifest:
    """Extract a ``.tar.gz`` backup's db + file trees into the live vault root, atomically.

    The restore is staged under the vault root and swapped into place with
    same-filesystem renames, so a mid-restore I/O failure (ENOSPC, EIO, an
    interrupt) NEVER leaves the live source-of-record trees destroyed: each
    live component is renamed aside before its replacement is moved in, and any
    failure rolls every swap back. The vault is made to MIRROR the backup —
    trees present live but absent from the backup are removed — so the restored
    index never disagrees with what is on disk.

    Caller is responsible for confirming an overwrite of a populated vault.

    Security: extraction uses ``filter="data"`` (Python 3.12+) to prevent
    path-traversal attacks.
    """
    verify_backup(src)
    root = vault_root()
    root.mkdir(parents=True, exist_ok=True)
    manifest = BackupManifest()

    staging = root / ".restore-staging"
    _remove(staging)
    staging.mkdir()

    # Components to swap in: (live destination, staged source or None).
    # None source = remove the live component (mirror a backup that omits it).
    swaps: list[tuple[Path, Path | None]] = []
    moved_aside: list[tuple[Path, Path]] = []  # (live, .restore-old)
    placed: list[Path] = []
    try:
        # 1. Determine what is in the archive (names are relative to vault root).
        with tarfile.open(src, "r:gz") as tar:
            tar_names = set(tar.getnames())
            # Extract to staging — path-traversal safe via filter="data".
            # A corrupt archive or a path-traversal member (AbsoluteLinkError,
            # LinkOutsideDestinationError, etc.) raises tarfile.TarError here;
            # translate to BackupError so the caller's except-BackupError block
            # handles it cleanly and the rollback below still runs.
            try:
                tar.extractall(path=staging, filter="data")
            except (tarfile.TarError, OSError) as exc:
                raise BackupError(f"corrupt or unsafe backup archive {src}: {exc}") from exc

        # 2. Build the swap list from what actually landed in staging.
        #    db is always present (verify_backup guarantees it).
        swaps.append((root / _DB_NAME, staging / _DB_NAME))

        for name in _TREE_NAMES:
            if (staging / name).is_dir():
                swaps.append((root / name, staging / name))
            else:
                swaps.append((root / name, None))  # absent in backup → remove live

        if (staging / _MASTER_KEY_NAME).exists():
            os.chmod(staging / _MASTER_KEY_NAME, 0o600)
            swaps.append((root / _MASTER_KEY_NAME, staging / _MASTER_KEY_NAME))

        # 3. Atomic swap: move each live component aside, then rename the staged
        #    replacement in. Same-filesystem renames are atomic and fast.
        for dest, staged in swaps:
            if dest.exists() or dest.is_symlink():
                aside = dest.with_name(dest.name + ".restore-old")
                _remove(aside)
                os.replace(dest, aside)
                moved_aside.append((dest, aside))
            if staged is not None:
                os.replace(staged, dest)
                placed.append(dest)
    except BaseException:
        # Roll back: drop anything we placed, move every aside original back.
        for dest in placed:
            _remove(dest)
        for dest, aside in moved_aside:
            with contextlib.suppress(OSError):
                os.replace(aside, dest)
        _remove(staging)
        raise

    # Success: discard the aside originals and the staging dir.
    for _dest, aside in moved_aside:
        _remove(aside)
    _remove(staging)

    manifest.db = True
    manifest.trees = [n for n in _TREE_NAMES if (root / n).is_dir()]
    manifest.master_key = _MASTER_KEY_NAME in tar_names
    return manifest
