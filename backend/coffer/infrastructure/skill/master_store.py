"""Filesystem manager for the canonical skill store at `~/.coffer/skills/`.

The master is the single editable source of truth for every managed skill.
Per-agent visibility is realised by `sync_engine` writing directory links
into each agent's skill_dir. Master operations are atomic where it matters
(create-on-import, replace-on-update) by staging into sibling temp dirs and
renaming.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime

# Defence-in-depth: even if a caller skips the surface-layer name guard, the
# master store still rejects names that could escape ``self._root``. Path
# separators on either OS, parent traversal, or absolute paths must never
# resolve a folder outside ``~/.coffer/skills/``.
_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.\-]+$")
_NAME_MAX_LEN = 64

# Never copy a `.git` directory into the canonical store: a skill imported from
# a path inside a checkout would otherwise drag that repository's whole history
# into ``~/.coffer/skills/<name>/``, and the managed copy is a snapshot, not a
# working tree.
_IGNORE_VCS = shutil.ignore_patterns(".git")


def _ensure_safe_name(name: str) -> None:
    if (
        not name
        or len(name) > _NAME_MAX_LEN
        or name in (".", "..")
        or "/" in name
        or "\\" in name
        or not _NAME_PATTERN.match(name)
    ):
        raise ValueError(f"unsafe skill name: {name!r}")


def default_master_root() -> pathlib.Path:
    """`$HOME/.coffer/skills/` — Coffer's canonical store root."""
    home = pathlib.Path(os.environ.get("HOME", os.path.expanduser("~")))
    return home / ".coffer" / "skills"


@dataclass(frozen=True)
class MasterPaths:
    """Resolved paths for one managed skill."""

    name: str
    folder: pathlib.Path
    skill_md: pathlib.Path
    meta_json: pathlib.Path


class MasterStore:
    """CRUD over Coffer's canonical skill folder tree."""

    def __init__(self, root: pathlib.Path | None = None) -> None:
        self._root = (root or default_master_root()).resolve()

    @property
    def root(self) -> pathlib.Path:
        return self._root

    def ensure_root(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)

    def paths_for(self, name: str) -> MasterPaths:
        _ensure_safe_name(name)
        folder = self._root / name
        return MasterPaths(
            name=name,
            folder=folder,
            skill_md=folder / "SKILL.md",
            meta_json=folder / ".coffer.meta.json",
        )

    def exists(self, name: str) -> bool:
        return self.paths_for(name).folder.is_dir()

    def copy_in(
        self,
        *,
        src: pathlib.Path,
        name: str,
        meta: dict[str, object] | None = None,
    ) -> MasterPaths:
        """Copy `src` directory tree into `<root>/<name>/`.

        Fails if `<root>/<name>/` already exists. Atomic via stage-then-rename.
        """
        self.ensure_root()
        dst = self.paths_for(name).folder
        if dst.exists():
            raise FileExistsError(f"master folder already exists: {dst}")
        with tempfile.TemporaryDirectory(prefix="coffer-master-stage-", dir=self._root) as tmp:
            staged = pathlib.Path(tmp) / name
            shutil.copytree(src, staged, symlinks=False, ignore=_IGNORE_VCS)
            if meta is not None:
                (staged / ".coffer.meta.json").write_text(
                    json.dumps(meta, default=_json_default, indent=2),
                    encoding="utf-8",
                )
            os.replace(staged, dst)
        return self.paths_for(name)

    def atomic_replace(
        self,
        *,
        src: pathlib.Path,
        name: str,
        meta: dict[str, object] | None = None,
    ) -> MasterPaths:
        """Replace `<root>/<name>/` with `src` contents atomically.

        Existing folder is moved aside, new content is renamed in, the
        old folder is then deleted. If the swap fails, the original is
        restored.
        """
        self.ensure_root()
        target = self.paths_for(name).folder
        if not target.is_dir():
            return self.copy_in(src=src, name=name, meta=meta)
        with tempfile.TemporaryDirectory(prefix="coffer-master-swap-", dir=self._root) as tmp:
            staged = pathlib.Path(tmp) / name
            shutil.copytree(src, staged, symlinks=False, ignore=_IGNORE_VCS)
            if meta is not None:
                (staged / ".coffer.meta.json").write_text(
                    json.dumps(meta, default=_json_default, indent=2),
                    encoding="utf-8",
                )
            backup = pathlib.Path(tmp) / f"{name}.bak"
            os.replace(target, backup)
            try:
                os.replace(staged, target)
            except OSError:
                # restore
                os.replace(backup, target)
                raise
        return self.paths_for(name)

    def rename(self, *, old_name: str, new_name: str) -> MasterPaths:
        """Move `<root>/<old_name>/` to `<root>/<new_name>/`.

        The store is keyed by the skill's NAME, which is a label the user may
        change (ADR resource-identity-is-an-immutable-uid), so the folder has
        to travel with it. Both names go through ``_ensure_safe_name`` via
        ``paths_for``, so a rename can no more escape the root than an import
        can.

        Deliberately a single ``os.rename`` within one directory: on POSIX and
        on NTFS that is atomic, so there is no observable moment in which the
        skill exists under both names or under neither. That is what lets the
        caller treat "this raised" as "nothing moved".

        Raises ``FileNotFoundError`` when no folder answers to ``old_name``
        and ``FileExistsError`` when something already occupies ``new_name``.
        The second check is not redundant: POSIX ``rename`` would silently
        replace an existing EMPTY directory at the destination, and silently
        destroying whatever sits there is the opposite of what a label edit
        should be allowed to do.
        """
        src = self.paths_for(old_name).folder
        dst = self.paths_for(new_name).folder
        if not src.is_dir():
            raise FileNotFoundError(f"no master folder for skill {old_name!r}: {src}")
        if dst.exists() or dst.is_symlink():
            raise FileExistsError(f"master folder already exists: {dst}")
        os.rename(src, dst)
        return self.paths_for(new_name)

    def delete(self, name: str) -> None:
        target = self.paths_for(name).folder
        if target.is_dir():
            shutil.rmtree(target)

    def find_orphans(self, known_names: set[str]) -> list[str]:
        """Folders on disk that the DB doesn't know about."""
        if not self._root.is_dir():
            return []
        return sorted(
            p.name for p in self._root.iterdir() if p.is_dir() and p.name not in known_names
        )


def _json_default(o: object) -> object:
    if isinstance(o, datetime):
        return o.astimezone(UTC).isoformat()
    if isinstance(o, pathlib.PurePath):
        return str(o)
    raise TypeError(f"unserialisable: {type(o)!r}")
