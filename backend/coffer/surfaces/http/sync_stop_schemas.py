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
from coffer.surfaces.http.handoff_schemas import HandoffOut
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
    #: An encrypted secret (``secret/*.enc``): answered with one side or the
    #: other only — no editor copy, no agent merge.
    secret: bool = False
    #: Whether an agent may be asked to merge it (never a secret, never a
    #: same-name or changed-and-deleted conflict).
    agent_mergeable: bool = False
    #: Once it was handed to an agent: ``handed_off`` (the agent has not
    #: written a merge yet) or ``merged_by_agent`` (a merge is saved, to be
    #: checked). Never an answer by itself: the file stays unresolved until it
    #: is marked resolved (``answer`` ``edited``).
    agent_state: Literal["handed_off", "merged_by_agent"] | None = None
    #: When it was handed over, the agent (a label) and the Coffer
    #: conversation, if the caller named them.
    agent_handed_at: str | None = None
    agent_name: str | None = None
    agent_conversation_id: str | None = None
    #: When the agent's merge was saved (``merged_by_agent`` only).
    agent_merged_at: str | None = None


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
    #: The hand-merge copy as it is saved now, once it exists.
    edited: str | None = None
    #: An agent's merge (the saved copy, no marker left) and the unified diff
    #: from this machine's version to it; set while ``agent_state`` is
    #: ``merged_by_agent``.
    merged: str | None = None
    merged_diff: str | None = None


class HandoffIn(BaseModel):
    """Which files to hand to an agent (every file an agent may merge when
    ``paths`` is omitted). ``agent`` and ``conversation_id`` are what the
    caller opened the prompt in, kept for the file's merged state; send the
    request again with them once the conversation exists."""

    paths: list[str] | None = Field(default=None, min_length=1)
    agent: str | None = Field(default=None, max_length=64)
    conversation_id: str | None = Field(default=None, max_length=128)


class AgentHandoffOut(BaseModel):
    handoff: HandoffOut
    #: The files the prompt covers.
    paths: list[str]


class JoinChoiceIn(BaseModel):
    path: str = Field(min_length=1)
    answer: Literal["mine", "theirs", "edited"]


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
    commit this machine last converged at; ``replace``: the remote holds an
    older layout and this vault replaces it (``deleted`` lists, capped, what
    goes away; ``deleted_total`` counts it)."""

    kind: Literal["empty", "new", "returning", "replace"]
    remote_tip: str | None
    pushed_by: str | None
    pushed_at: str | None
    pulled: list[AreaCountOut]
    same: int
    differ: list[str]
    pushed: list[AreaCountOut]
    deleted: list[str]
    deleted_total: int
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


class ValueShapeOut(BaseModel):
    """What a masked value looks like, never what it is."""

    length: int
    classes: list[Literal["lower", "upper", "digit", "symbol"]]
    #: A well-known token format's public prefix (``ghp_``, ``sk-``) or a
    #: URL's scheme; the masked text keeps it.
    prefix: str | None = None
    #: ``reference``: names joined by dots, such as an environment-variable
    #: read; ``placeholder``: holds a placeholder ``word``; ``repeated``: one
    #: or two characters over and over.
    hint: Literal["reference", "placeholder", "repeated"] | None = None
    word: str | None = None


class MaskedValueOut(BaseModel):
    """One masked value on a line, ``[start, end)`` in the masked text."""

    start: int
    end: int
    key: str
    shape: ValueShapeOut


class MaskedLineOut(BaseModel):
    number: int
    #: The line with every plaintext value replaced by ``•`` (same length).
    text: str
    values: list[MaskedValueOut] = []


class PlaintextContextOut(BaseModel):
    """A place the last round found a plaintext secret, in its file: the lines
    around it with every value masked, whether the remote holds the file
    (``added`` / ``modified``) and the flagged line already, and for a
    modified file its masked change against the remote's copy. Never a
    value."""

    path: str
    line: int
    key: str
    change: Literal["added", "modified"]
    on_remote: bool
    lines: list[MaskedLineOut]
    #: Unified diff against the remote's copy, masked; ``None`` for an added
    #: file or one too large to show line by line.
    diff: str | None = None
    added: int = 0
    removed: int = 0


__all__ = [
    "AgentHandoffOut",
    "AreaCountOut",
    "BreachOut",
    "ConflictFileOut",
    "EditorCopyOut",
    "FileAnswerIn",
    "FilePathIn",
    "FileVersionsOut",
    "HandoffIn",
    "HoldGroupOut",
    "HoldOut",
    "JoinChoiceIn",
    "JoinChoicesIn",
    "JoinChoicesOut",
    "JoinPreviewOut",
    "MaskedLineOut",
    "MaskedValueOut",
    "PlaintextContextOut",
    "RollbackPlanOut",
    "StopStateOut",
    "StoppedRoundOut",
    "ValueShapeOut",
]
