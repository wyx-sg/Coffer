"""Move the vault out of a synchronised folder (spec vault-sync "Move the
vault out of a synchronised folder").

The vault's path is fixed: ``~/.coffer/vault`` (``vault_home.vault_root``) is
what every part of the daemon computes, so a vault that lives elsewhere is
reached *through* that path, and moving it never changes a path any holder
has. Moving therefore means: put the folder at the new place, check the git
repository there, and make ``~/.coffer/vault`` lead to it — a real folder when
the new place is that path itself, otherwise a symbolic link. The detector of
the "Cloud folder" problem resolves links, so it reads the new place.

The old folder is left in place and empty; the person deletes it.
"""

from __future__ import annotations

import contextlib
import os
import shutil
from pathlib import Path

from coffer.domain.sync.errors import (
    SyncVaultMoveFailed,
    SyncVaultTargetInCloud,
    SyncVaultTargetInvalid,
    SyncVaultTargetNotEmpty,
)
from coffer.infrastructure.sync.cloud_folder import synchroniser_of
from coffer.infrastructure.vault import git
from coffer.infrastructure.vault.home import vault_root


class VaultMover:
    def __init__(self, *, home: Path | None = None) -> None:
        self._home = home

    def _vault(self) -> Path:
        return vault_root(self._home)

    def _user_home(self) -> Path:
        return self._home if self._home is not None else Path.home()

    def real_path(self) -> str:
        """Where the vault's files really are (links resolved)."""
        return str(self._vault().resolve(strict=False))

    def default_path(self) -> str:
        """Where a move offers to put it: ``~/.coffer/vault`` as a real folder."""
        return str(self._vault())

    # --- checks -----------------------------------------------------------------

    def _validated(self, to: str) -> tuple[Path, Path, Path]:
        """``(link, source, target)`` for a move to ``to``, or the error that
        says why not. ``link`` is ``~/.coffer/vault``; ``source`` where the
        vault really is; ``target`` where its files will be."""
        link = self._vault()
        source = link.resolve(strict=False)
        raw = Path(to.strip()).expanduser() if to.strip() else None
        if raw is None or not raw.is_absolute():
            raise SyncVaultTargetInvalid(f"choose an absolute folder, not {to!r}")
        wanted = Path(os.path.normpath(raw))
        # The default is the vault's own path: a real folder replaces the link.
        own = link.parent.resolve(strict=False) / link.name
        is_own = wanted.parent.resolve(strict=False) / wanted.name == own
        target = own if is_own else wanted.resolve(strict=False)
        if target == source or source in target.parents or target in source.parents:
            raise SyncVaultTargetInvalid(
                "the new folder must be a different folder, outside the current vault"
            )
        # The link at the default path leads into the folder being left; what
        # counts is where a real folder there would sit.
        probe = target.parent if target.is_symlink() else target
        if (tool := synchroniser_of(probe, home=self._user_home())) is not None:
            raise SyncVaultTargetInCloud(str(target), tool)
        if not (target.parent.is_dir() and os.access(target.parent, os.W_OK | os.X_OK)):
            raise SyncVaultTargetInvalid(f"{target.parent} is not a folder Coffer can write in")
        # The link occupies the default path; it is replaced, not "in the way".
        occupied = target.exists() and not (target == own and link.is_symlink())
        if occupied and (not target.is_dir() or any(target.iterdir())):
            raise SyncVaultTargetNotEmpty(f"{target} is not empty")
        return link, source, target

    def check(self, to: str) -> None:
        self._validated(to)

    # --- the move ---------------------------------------------------------------

    def move(self, to: str) -> tuple[str, str]:
        """Move the vault to ``to``. The caller holds every writer of the vault
        off. On any failure the vault is back where it was."""
        link, source, target = self._validated(to)
        if not source.is_dir():
            raise SyncVaultMoveFailed(f"the vault folder {source} does not exist")
        before = _fingerprint(source)
        old_link = os.readlink(link) if link.is_symlink() else None
        try:
            if link.is_symlink() and target == link.parent.resolve() / link.name:
                link.unlink()  # the new folder takes the link's own place
            _transfer(source, target)
            if _fingerprint(target) != before:
                raise SyncVaultMoveFailed("the vault at its new place differs from the old one")
            if source.exists():  # copied across filesystems: empty the old one
                _clear(source)
                if source == link:
                    source.rmdir()
            if target != link:
                self._point_link_at(link, target)
        except Exception as exc:
            self._roll_back(link, source, target, old_link)
            if isinstance(exc, SyncVaultMoveFailed):
                raise
            raise SyncVaultMoveFailed(f"could not move the vault: {exc}") from exc
        # The old folder stays, empty, for the person to delete.
        if source != link and source != target:
            with contextlib.suppress(OSError):
                source.mkdir(parents=True, exist_ok=True)
        return str(source), str(target)

    @staticmethod
    def _point_link_at(link: Path, target: Path) -> None:
        if link.is_symlink():
            link.unlink()
        elif link.exists():
            raise SyncVaultMoveFailed(f"{link} is a folder, not a link")
        link.symlink_to(target, target_is_directory=True)

    @staticmethod
    def _roll_back(link: Path, source: Path, target: Path, old_link: str | None) -> None:
        """Best effort: put the files and the link back as they were."""
        with contextlib.suppress(OSError):
            if target.exists() and not source.exists():
                _transfer(target, source)
            elif target.exists():
                shutil.rmtree(target, ignore_errors=True)
        with contextlib.suppress(OSError):
            if old_link is not None:
                if link.is_symlink():
                    link.unlink()
                if not link.exists():
                    link.symlink_to(old_link, target_is_directory=True)


def _transfer(source: Path, target: Path) -> None:
    """``source`` becomes ``target``: a rename on one filesystem, else a copy
    that leaves ``source`` as it was (the caller empties it once verified)."""
    if target.is_dir() and not any(target.iterdir()):
        target.rmdir()
    try:
        source.rename(target)
    except OSError:
        shutil.copytree(source, target, symlinks=True)
        # Cross-device: ``source`` is kept until the copy is verified.


def _clear(folder: Path) -> None:
    for child in folder.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        else:
            with contextlib.suppress(OSError):
                child.unlink()


def _fingerprint(root: Path) -> tuple[object, ...]:
    """What the git repository at ``root`` says about itself, plus a walk of
    its files: the move changed neither. A vault with no repository (not yet
    created) is only walked."""
    walk = sorted(
        (str(p.relative_to(root)), p.stat().st_size)
        for p in root.rglob("*")
        if p.is_file() and not p.is_symlink()
    )
    if not (root / ".git").exists():
        return (tuple(walk),)
    head = git.run(root, "rev-parse", "--verify", "-q", "HEAD", check=False).stdout
    status = git.run(root, "status", "--porcelain").stdout
    git.run(root, "fsck", "--connectivity-only", "--no-dangling")
    return (tuple(walk), head, status)
