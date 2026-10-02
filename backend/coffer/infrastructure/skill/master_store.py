"""Filesystem manager for the canonical skill store at ``~/.coffer/vault/skills/``.

The master is the single editable source of truth for every managed skill.
Per-agent visibility is realised by `sync_engine` writing directory links
into each agent's skill_dir. Master operations are atomic where it matters
(create-on-import, replace-on-update) by staging into sibling temp dirs and
renaming.

A skill's master folder sits in the vault (ADR storage-is-five-classes-by-nature)
— except Coffer's own ``coffer-guide``, which the running build renders at every
boot: it is derived output, so its folder is ``~/.coffer/derived/skills/<name>/``
and every link delivered for it points there. :meth:`MasterStore.paths_for` is
the one place that decides, so the seed, delivery and drift checks all agree.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime

from coffer.infrastructure.vault.home import content_root, derived_root, vault_root

_log = logging.getLogger(__name__)

# Defence-in-depth: even if a caller skips the surface-layer name guard, the
# master store still rejects names that could escape ``self._root``. Path
# separators on either OS, parent traversal, or absolute paths must never
# resolve a folder outside the store's root.
_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.\-]+$")
_NAME_MAX_LEN = 64

# Never copy a `.git` directory into the canonical store: a skill imported from
# a path inside a checkout would otherwise drag that repository's whole history
# into ``~/.coffer/vault/skills/<name>/``, and the managed copy is a snapshot, not a
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
    """``~/.coffer/vault/skills/`` — Coffer's canonical store root, resolved
    from ``HOME`` at every call (there is no per-tree override)."""
    return vault_root() / "skills"


def default_derived_root() -> pathlib.Path:
    """``~/.coffer/derived/skills/`` — where the rendered builtin skills live."""
    return derived_root() / "skills"


#: Skills Coffer renders from the running build rather than the user authors.
#: The name is a literal here because this package may not import the
#: knowledge layer that renders it (``application.knowledge.guide_render``,
#: import-linter's cross-kind fences); it is the only such skill.
DERIVED_SKILL_NAMES = frozenset({"coffer-guide"})


@dataclass(frozen=True)
class MasterPaths:
    """Resolved paths for one managed skill."""

    name: str
    folder: pathlib.Path
    skill_md: pathlib.Path
    meta_json: pathlib.Path


class MasterStore:
    """CRUD over Coffer's canonical skill folder tree."""

    def __init__(
        self, root: pathlib.Path | None = None, *, derived: pathlib.Path | None = None
    ) -> None:
        self._root = (root or default_master_root()).resolve()
        self._derived = (derived or default_derived_root()).resolve()

    @property
    def root(self) -> pathlib.Path:
        return self._root

    @property
    def derived_root(self) -> pathlib.Path:
        """Where the builtin skills' folders live (``DERIVED_SKILL_NAMES``)."""
        return self._derived

    @property
    def backup_root(self) -> pathlib.Path:
        """``~/.coffer/content/backup/skills/``: where a folder moved out of an
        agent's link path, or out of the store, is kept. Content, not vault: a
        set-aside copy is the person's only copy but is not configuration to
        sync (ADR storage-is-five-classes-by-nature)."""
        return content_root() / "backup" / "skills"

    def ensure_root(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)

    def _parent(self, name: str) -> pathlib.Path:
        """The directory ``name``'s folder sits in: derived for a builtin skill."""
        return self._derived if name in DERIVED_SKILL_NAMES else self._root

    def paths_for(self, name: str) -> MasterPaths:
        _ensure_safe_name(name)
        folder = self._parent(name) / name
        return MasterPaths(
            name=name,
            folder=folder,
            skill_md=folder / "SKILL.md",
            meta_json=folder / ".coffer.meta.json",
        )

    def _staging(self, prefix: str) -> tempfile.TemporaryDirectory[str]:
        """A scratch directory on the same filesystem as the store but outside
        the vault: a crash mid-copy must not leave a folder in the vault, where
        it would be reported as an orphan skill and could be committed and synced."""
        self._derived.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(prefix=f".{prefix}", dir=self._derived)

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
        dst.parent.mkdir(parents=True, exist_ok=True)
        with self._staging("coffer-master-stage-") as tmp:
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
        with self._staging("coffer-master-swap-") as tmp:
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

    def delete(self, name: str) -> None:
        target = self.paths_for(name).folder
        if target.is_dir():
            shutil.rmtree(target)

    def find_orphans(self, known_names: set[str]) -> list[str]:
        """Folders on disk that the DB doesn't know about.

        A folder whose name is not a safe skill name (a stray ``my skill`` or
        ``.tmp``) is left out: every other operation refuses such a name, and
        passing it on would make the whole link target (and the orphan list)
        fail until the folder is renamed. It is logged, not delivered or adopted.
        """
        if not self._root.is_dir():
            return []
        names: list[str] = []
        for p in self._root.iterdir():
            if not p.is_dir() or p.name in known_names:
                continue
            try:
                _ensure_safe_name(p.name)
            except ValueError:
                _log.warning("skill.master_store.unsafe_folder", extra={"folder": p.name})
                continue
            names.append(p.name)
        return sorted(names)


def _json_default(o: object) -> object:
    if isinstance(o, datetime):
        return o.astimezone(UTC).isoformat()
    if isinstance(o, pathlib.PurePath):
        return str(o)
    raise TypeError(f"unserialisable: {type(o)!r}")
