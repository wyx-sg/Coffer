"""Wire shapes for a round waiting for a person — a stop on conflicts, a
hold, a join and its differing files, a rollback
(spec vault-sync "Hold a round that would lose too much", "Report a join
before applying it", "Snapshot before checking out and roll a round back from it").

A file's path is vault-relative and always travels in a body or a query,
never a path segment: it contains slashes.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from coffer.domain.sync.stops import Answer, ConflictReason
from coffer.surfaces.http.sync_schemas import SyncChangeOut


class ConflictFileOut(BaseModel):
    path: str
    area: str
    reason: ConflictReason
    #: When this machine and the other last changed the file, and which
    #: machine the other change came from.
    ours_time: str | None
    theirs_time: str | None
    theirs_machine: str | None
    #: For a same-name or duplicate-uid conflict: the other path involved.
    other_path: str | None
    answer: Answer | None
    #: The hand-merge copy, once opened in the editor.
    editor_path: str | None


class BreachOut(BaseModel):
    area: str
    lost: int
    total: int


class HoldGroupOut(BaseModel):
    """The held files under one folder, and how many files it held."""

    folder: str
    paths: list[str]
    total: int


class HoldOut(BaseModel):
    #: ``incoming``: the other machine's changes would delete these here;
    #: ``outgoing``: this machine's commits would delete them on the remote.
    direction: Literal["incoming", "outgoing"]
    breaches: list[BreachOut]
    paths: list[str]
    groups: list[HoldGroupOut]
    #: The machines whose changes would delete them, by label.
    machines: list[str]
    confirmed: bool


class StoppedRoundOut(BaseModel):
    kind: Literal["conflicts", "hold"]
    raised_at: str
    local: str
    remote: str
    join: str | None
    files: list[ConflictFileOut]
    unanswered: int
    hold: HoldOut | None


class StopStateOut(BaseModel):
    stopped: bool
    round: StoppedRoundOut | None


class FileAnswerIn(BaseModel):
    path: str = Field(min_length=1)
    answer: Answer


class FilePathIn(BaseModel):
    path: str = Field(min_length=1)


class EditorCopyOut(BaseModel):
    path: str
    #: The absolute path of the marked-up copy to edit; the OS-open action
    #: (``POST /api/v1/open``) opens it.
    editor_path: str


class FileVersionsOut(BaseModel):
    path: str
    ours: str | None
    theirs: str | None
    base: str | None
    #: What taking the other machine's version changes on this machine.
    take_theirs: str
    binary: bool


class JoinChoiceIn(BaseModel):
    path: str = Field(min_length=1)
    answer: Literal["mine", "theirs"]


class JoinChoicesIn(BaseModel):
    choices: list[JoinChoiceIn] = Field(min_length=1)


class JoinChoicesOut(BaseModel):
    files: list[ConflictFileOut]


class AreaCountOut(BaseModel):
    area: str
    files: int


class JoinPreviewOut(BaseModel):
    """What joining would do. ``empty``: the remote is empty and this vault is
    pushed whole; ``new``: the union is taken, nothing deleted, differing
    files left here until chosen; ``returning``: a three-way merge from the
    commit this machine last converged at."""

    kind: Literal["empty", "new", "returning"]
    remote_tip: str | None
    pushed_by: str | None
    pushed_at: str | None
    pulled: list[AreaCountOut]
    same: int
    differ: list[str]
    pushed: list[AreaCountOut]
    deleted: list[str]
    conflicts: list[str]
    same_name: list[str]
    refused: str | None
    pulled_files: int
    pushed_files: int


class RollbackPlanOut(BaseModel):
    snapshot: str
    snapshot_commit: str
    snapshot_time: str | None
    #: Each file rolling back puts back, and what it becomes.
    reverses: list[SyncChangeOut]
    #: Files edited since the round: left as they are.
    kept: list[str]


__all__ = [
    "AreaCountOut",
    "BreachOut",
    "ConflictFileOut",
    "EditorCopyOut",
    "FileAnswerIn",
    "FilePathIn",
    "FileVersionsOut",
    "HoldGroupOut",
    "HoldOut",
    "JoinChoiceIn",
    "JoinChoicesIn",
    "JoinChoicesOut",
    "JoinPreviewOut",
    "RollbackPlanOut",
    "StopStateOut",
    "StoppedRoundOut",
]
