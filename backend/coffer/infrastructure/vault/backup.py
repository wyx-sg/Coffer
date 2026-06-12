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


def _copy_db(src_root: Path, dest_root: Path, manifest: BackupManifest) -> None:
    src_db = src_root / _DB_NAME
    if src_db.exists():
        dest_root.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_db, dest_root / _DB_NAME)
        manifest.db = True


def _copy_trees(src_root: Path, dest_root: Path, manifest: BackupManifest) -> None:
    for name in _TREE_NAMES:
        src_tree = src_root / name
        if src_tree.is_dir():
            # Replace, never merge: a file deleted from the live tree must not
            # survive in a re-used backup dest and get resurrected on restore.
            dest_tree = dest_root / name
            if dest_tree.exists():
                shutil.rmtree(dest_tree)
            shutil.copytree(src_tree, dest_tree)
            manifest.trees.append(name)


def create_backup(dest: Path, *, include_master_key: bool = False) -> BackupManifest:
    """Copy the live vault (db + file trees) into ``dest``.

    ``dest`` is created if absent. Raises :class:`BackupError` when there is no
    vault to back up (neither db nor any file tree exists). The master key is
    only copied when ``include_master_key`` is True.
    """
    root = vault_root()
    has_db = (root / _DB_NAME).exists()
    has_tree = any((root / name).is_dir() for name in _TREE_NAMES)
    if not has_db and not has_tree:
        raise BackupError(f"no vault found at {root} — nothing to back up")

    dest.mkdir(parents=True, exist_ok=True)
    manifest = BackupManifest()
    _copy_db(root, dest, manifest)
    _copy_trees(root, dest, manifest)

    if include_master_key:
        src_key = root / _MASTER_KEY_NAME
        if src_key.exists():
            shutil.copy2(src_key, dest / _MASTER_KEY_NAME)
            os.chmod(dest / _MASTER_KEY_NAME, 0o600)
            manifest.master_key = True

    return manifest


def verify_backup(src: Path) -> None:
    """Reject a source dir that is not a recognisable vault backup.

    Requires at least ``coffer.db`` (the one component every backup carries).
    Raises :class:`BackupError` otherwise — checked before any clobbering.
    """
    if not src.is_dir():
        raise BackupError(f"backup source {src} is not a directory")
    if not (src / _DB_NAME).exists():
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
    """Re-place a backup's db + file trees into the live vault root, atomically.

    The restore is staged under the vault root and swapped into place with
    same-filesystem renames, so a mid-restore I/O failure (ENOSPC, EIO, an
    interrupt) NEVER leaves the live source-of-record trees destroyed: each
    live component is renamed aside before its replacement is moved in, and any
    failure rolls every swap back. The vault is made to MIRROR the backup —
    trees present live but absent from the backup are removed — so the restored
    index never disagrees with what is on disk.

    Caller is responsible for confirming an overwrite of a populated vault.
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
        # 1. Stage everything from the backup (the expensive, failure-prone copy
        #    happens entirely off to the side; the live vault is untouched here).
        shutil.copy2(src / _DB_NAME, staging / _DB_NAME)
        swaps.append((root / _DB_NAME, staging / _DB_NAME))
        for name in _TREE_NAMES:
            if (src / name).is_dir():
                shutil.copytree(src / name, staging / name)
                swaps.append((root / name, staging / name))
            else:
                swaps.append((root / name, None))  # absent in backup → remove live
        if (src / _MASTER_KEY_NAME).exists():
            shutil.copy2(src / _MASTER_KEY_NAME, staging / _MASTER_KEY_NAME)
            os.chmod(staging / _MASTER_KEY_NAME, 0o600)
            swaps.append((root / _MASTER_KEY_NAME, staging / _MASTER_KEY_NAME))

        # 2. Atomic swap: move each live component aside, then rename the staged
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
    manifest.trees = [n for n in _TREE_NAMES if (src / n).is_dir()]
    manifest.master_key = (src / _MASTER_KEY_NAME).exists()
    return manifest
