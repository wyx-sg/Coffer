"""Where a source waits to be confirmed.

Spec skill-manager "Add skills from an archive": nothing is copied into the
master store or registered until the user confirms, and the staging area is
removed either way. A stage is one directory under a per-daemon root in the
system's temp space (never under ``~/.coffer``, so vault sync cannot see it)
plus what was found there, held in memory under a random id:

- an **import** stage (a folder, an archive or a Git checkout), confirmed into
  one or more skills or cancelled;
- an **update** stage (a Git-imported skill's pinned and new folders side by
  side), applied or cancelled.

A stage nobody confirms is removed an hour after it was made, on the next call
that touches the registry. A daemon restart forgets them all, which is right:
nothing was promised, and the directories go with the temp root.
"""

from __future__ import annotations

import pathlib
import secrets
import shutil
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from coffer.domain.skill.source import ImportedSource
from coffer.domain.skill_source_errors import SkillStagingNotFound

#: How long an unconfirmed stage is kept.
STAGE_TTL_S = 3600.0

StageKind = Literal["folder", "archive", "git"]


@dataclass(frozen=True)
class StagedSkill:
    """One skill a stage found, valid or not, and whether its name is taken."""

    folder: str  # relative to the stage's root; "." for the root itself
    path: pathlib.Path
    name: str | None
    description: str | None
    file_count: int
    size_bytes: int
    valid: bool
    reason: str | None = None
    message: str | None = None
    taken: bool = False
    #: The name belongs to a skill Coffer generates, which nothing may replace.
    protected: bool = False


@dataclass
class ImportStage:
    id: str
    kind: StageKind
    #: What the person handed over: the folder, the archive's file name, the URL.
    label: str
    skills: list[StagedSkill]
    #: The provenance each chosen skill is registered with.
    source_for: Callable[[StagedSkill], ImportedSource]
    dir: pathlib.Path | None = None
    #: Git only: the ref asked for, the subpath looked under and the commit.
    ref: str | None = None
    subpath: str = ""
    commit: str | None = None
    created: float = field(default_factory=time.monotonic)


@dataclass
class UpdateStage:
    id: str
    skill_uid: str
    dir: pathlib.Path
    from_commit: str
    to_commit: str
    #: The pinned commit's folder (``None`` when that commit is gone upstream).
    pinned: pathlib.Path | None
    incoming: pathlib.Path
    content_hash: str
    preview: Any = None
    created: float = field(default_factory=time.monotonic)


Stage = ImportStage | UpdateStage


class StagingRegistry:
    """The stages in flight, and the directories they own."""

    def __init__(
        self,
        *,
        root: pathlib.Path | None = None,
        ttl_s: float = STAGE_TTL_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._root = root
        self._ttl = ttl_s
        self._clock = clock
        self._stages: dict[str, Stage] = {}

    def _base(self) -> pathlib.Path:
        if self._root is None:
            self._root = pathlib.Path(tempfile.mkdtemp(prefix="coffer-skill-staging-"))
        self._root.mkdir(parents=True, exist_ok=True)
        return self._root

    def new_dir(self) -> tuple[str, pathlib.Path]:
        """A fresh id and an empty directory for it."""
        self.sweep()
        stage_id = secrets.token_hex(12)
        path = self._base() / stage_id
        path.mkdir()
        return stage_id, path

    def new_id(self) -> str:
        self.sweep()
        return secrets.token_hex(12)

    def put(self, stage: Stage) -> Stage:
        stage.created = self._clock()
        self._stages[stage.id] = stage
        return stage

    def get(self, stage_id: str) -> Stage:
        self.sweep()
        stage = self._stages.get(stage_id)
        if stage is None:
            raise SkillStagingNotFound(stage_id)
        return stage

    def discard(self, stage_id: str) -> bool:
        """Forget a stage and remove its directory; ``False`` when there was none."""
        stage = self._stages.pop(stage_id, None)
        if stage is None:
            return False
        remove_dir(stage.dir)
        return True

    def sweep(self) -> None:
        now = self._clock()
        for stage_id in [s.id for s in self._stages.values() if now - s.created > self._ttl]:
            self.discard(stage_id)

    def close(self) -> None:
        """Remove every stage and the root (daemon shutdown)."""
        for stage_id in list(self._stages):
            self.discard(stage_id)
        if self._root is not None:
            shutil.rmtree(self._root, ignore_errors=True)

    def __contains__(self, stage_id: object) -> bool:
        return stage_id in self._stages


def remove_dir(path: pathlib.Path | None) -> None:
    if path is not None:
        shutil.rmtree(path, ignore_errors=True)


__all__ = [
    "STAGE_TTL_S",
    "ImportStage",
    "Stage",
    "StagedSkill",
    "StagingRegistry",
    "UpdateStage",
    "remove_dir",
]
