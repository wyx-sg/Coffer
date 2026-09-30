"""What one sync round did (spec vault-sync "Record every round").

A round pulls, applies, then pushes. Its record says which of those happened,
what came in (the commits and the files applied here), what went out, the
range of commits it moved the vault across, the safety snapshot it took, and —
when it stopped or failed — why, in words a person can act on. The Sync page
folds consecutive rounds with nothing to do into one row; that is a matter of
presentation, and every round is still recorded.
"""

from __future__ import annotations

import dataclasses
from enum import StrEnum
from typing import Any


class RoundStatus(StrEnum):
    #: Nothing to pull and nothing to push.
    NOTHING_TO_DO = "nothing_to_do"
    PULLED = "pulled"
    PUSHED = "pushed"
    PULLED_AND_PUSHED = "pulled_and_pushed"
    #: Pulled and applied, but the remote refused the push.
    PUSH_FAILED = "push_failed"
    #: Any conflict: nothing checked out, nothing pushed.
    STOPPED = "stopped"
    #: The deletion breaker held the round.
    HELD = "held"
    #: A person's uncommitted edit is on a path the round would change.
    WAITING_ON_EDIT = "waiting_on_edit"
    #: The remote's layout needs the owner machine's upgrade first.
    WAITING_FOR_LAYOUT = "waiting_for_layout"
    #: This machine has never converged with the remote: join first.
    JOIN_REQUIRED = "join_required"
    JOINED = "joined"
    UNREACHABLE = "unreachable"
    AUTH_FAILED = "auth_failed"
    #: The vault is inside a folder another tool synchronises.
    PAUSED_CLOUD_FOLDER = "paused_cloud_folder"
    #: The remote was written by a newer Coffer's layout.
    REMOTE_TOO_NEW = "remote_too_new"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


#: Rounds that leave the vault in the state a person must look at.
NEEDS_PERSON = frozenset(
    {
        RoundStatus.STOPPED,
        RoundStatus.HELD,
        RoundStatus.WAITING_ON_EDIT,
        RoundStatus.JOIN_REQUIRED,
        RoundStatus.AUTH_FAILED,
        RoundStatus.PAUSED_CLOUD_FOLDER,
        RoundStatus.REMOTE_TOO_NEW,
    }
)


@dataclasses.dataclass(frozen=True)
class PulledCommit:
    version: str
    time: str
    machine: str | None
    files: int


@dataclasses.dataclass(frozen=True)
class AppliedChange:
    path: str
    #: ``added`` / ``modified`` / ``removed``.
    status: str


@dataclasses.dataclass(frozen=True)
class RoundRecord:
    status: RoundStatus
    started_at: str
    finished_at: str
    trigger: str = "timer"
    #: The commit range the vault moved across (``from..to``).
    from_commit: str | None = None
    to_commit: str | None = None
    snapshot: str | None = None
    pulled: tuple[PulledCommit, ...] = ()
    applied: tuple[AppliedChange, ...] = ()
    pushed: tuple[AppliedChange, ...] = ()
    #: The machines whose commits this round pulled, by label.
    with_machines: tuple[str, ...] = ()
    conflicts: int = 0
    held: int = 0
    #: For a failure: git's redacted message, and the path a waiting round names.
    detail: str | None = None
    path: str | None = None
    join: str | None = None
    #: The id the history store gave this record (``None`` until stored).
    id: int | None = None

    @property
    def pulled_files(self) -> int:
        return len(self.applied)

    @property
    def pushed_files(self) -> int:
        return len(self.pushed)

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for f in dataclasses.fields(self):
            value = getattr(self, f.name)
            if isinstance(value, tuple):
                value = (
                    [dataclasses.asdict(v) for v in value]
                    if value and dataclasses.is_dataclass(value[0])
                    else list(value)
                )
            elif isinstance(value, StrEnum):
                value = value.value
            out[f.name] = value
        return out

    @classmethod
    def from_json(cls, raw: dict[str, Any], *, id: int | None = None) -> RoundRecord:
        return cls(
            status=RoundStatus(raw["status"]),
            started_at=raw["started_at"],
            finished_at=raw["finished_at"],
            trigger=raw.get("trigger", "timer"),
            from_commit=raw.get("from_commit"),
            to_commit=raw.get("to_commit"),
            snapshot=raw.get("snapshot"),
            pulled=tuple(PulledCommit(**c) for c in raw.get("pulled") or ()),
            applied=tuple(AppliedChange(**c) for c in raw.get("applied") or ()),
            pushed=tuple(AppliedChange(**c) for c in raw.get("pushed") or ()),
            with_machines=tuple(raw.get("with_machines") or ()),
            conflicts=int(raw.get("conflicts") or 0),
            held=int(raw.get("held") or 0),
            detail=raw.get("detail"),
            path=raw.get("path"),
            join=raw.get("join"),
            id=id if id is not None else raw.get("id"),
        )


__all__ = ["NEEDS_PERSON", "AppliedChange", "PulledCommit", "RoundRecord", "RoundStatus"]
