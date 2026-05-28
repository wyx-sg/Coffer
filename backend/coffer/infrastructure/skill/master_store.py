"""Filesystem manager for the canonical skill store at `~/.coffer/skills/`.

The master is the single editable source of truth for every managed skill.
Per-agent visibility is realised by `sync_engine` writing directory links
into each agent's skill_dir. Master operations are atomic where it matters
(create-on-import, replace-on-update) by staging into sibling temp dirs and
renaming.
"""

from __future__ import annotations

import hashlib
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

# Never copy a `.git` directory into the canonical store. A git-sourced skill
# fetched with an empty subpath is the whole repository, so an unfiltered
# copytree would drag the entire `.git` history into ``~/.coffer/skills/<name>/``.
# Applying the ignore unconditionally is also correct for local imports, where
# a stray `.git` is likewise unwanted in the managed copy.
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

    def list_names(self) -> list[str]:
        if not self._root.is_dir():
            return []
        return sorted(p.name for p in self._root.iterdir() if p.is_dir())

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

    def rename(self, *, old: str, new: str) -> MasterPaths:
        """Rename `<root>/<old>/` to `<root>/<new>/`."""
        old_paths = self.paths_for(old)
        new_paths = self.paths_for(new)
        if not old_paths.folder.is_dir():
            raise FileNotFoundError(f"master folder missing: {old_paths.folder}")
        if new_paths.folder.exists():
            raise FileExistsError(f"target master folder exists: {new_paths.folder}")
        os.replace(old_paths.folder, new_paths.folder)
        return new_paths

    def delete(self, name: str) -> None:
        target = self.paths_for(name).folder
        if target.is_dir():
            shutil.rmtree(target)

    def skill_md_sha256(self, name: str) -> str | None:
        skill_md = self.paths_for(name).skill_md
        if not skill_md.is_file():
            return None
        return hashlib.sha256(skill_md.read_bytes()).hexdigest()

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
