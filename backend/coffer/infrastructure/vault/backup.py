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
            shutil.copytree(src_tree, dest_root / name, dirs_exist_ok=True)
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


def restore_backup(src: Path) -> BackupManifest:
    """Re-place a backup's db + file trees into the live vault root.

    Caller is responsible for confirming an overwrite of a populated vault.
    Existing trees are replaced wholesale (a removed file in the backup must not
    survive in the restored tree); the db is overwritten in place.
    """
    verify_backup(src)
    root = vault_root()
    root.mkdir(parents=True, exist_ok=True)
    manifest = BackupManifest()

    shutil.copy2(src / _DB_NAME, root / _DB_NAME)
    manifest.db = True

    for name in _TREE_NAMES:
        src_tree = src / name
        if src_tree.is_dir():
            dest_tree = root / name
            if dest_tree.exists():
                shutil.rmtree(dest_tree)
            shutil.copytree(src_tree, dest_tree)
            manifest.trees.append(name)

    src_key = src / _MASTER_KEY_NAME
    if src_key.exists():
        shutil.copy2(src_key, root / _MASTER_KEY_NAME)
        os.chmod(root / _MASTER_KEY_NAME, 0o600)
        manifest.master_key = True

    return manifest
