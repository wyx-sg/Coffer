"""A round that stopped for a person, and the answers they give
(ADR sync-applies-clean-merges-and-stops-on-any-conflict).

Any conflict stops the round **whole**: nothing is checked out and nothing is
pushed. The person answers each file — keep this machine's version, take the
other machine's, or open a marked-up copy in an editor and save the version
they want — and when every file has an answer the resolved tree goes through
the same guard, snapshot, checkout and push as a clean merge.

A stop is a question about one pair of commits. It records the local and
remote tips it was raised against; if either moves before the person answers,
the round is re-derived and asked again. Local writes keep being committed
meanwhile — only convergence waits.

A **hold** is the deletion breaker's stop: the round would lose more than it
may unattended, in one direction. The answers are "apply the deletions" or
"restore the files" (which keeps them here and pushes them back).

A **join choice** is different in kind: when a machine joins a remote it has
never converged with, a file both sides hold with different content has no
common base to merge from. Such files are left exactly as they are on this
machine and are not pushed until the person chooses, while rounds keep
running for everything else.
"""

from __future__ import annotations

import dataclasses
from enum import StrEnum
from typing import Any

from coffer.domain.sync.breaker import Breach


class Answer(StrEnum):
    MINE = "mine"
    THEIRS = "theirs"
    EDITED = "edited"


class ConflictReason(StrEnum):
    #: Both machines changed the file and git could not merge the changes.
    BOTH_CHANGED = "both_changed"
    #: One machine changed the file, the other deleted it.
    CHANGED_AND_DELETED = "changed_and_deleted"
    #: Two resources of one kind with the same name but different uids.
    SAME_NAME_DIFFERENT_UID = "same_name_different_uid"
    #: One uid at two paths after the merge (a rename git could not pair).
    DUPLICATE_UID = "duplicate_uid"
    #: The merged file fails validation.
    INVALID_MERGE = "invalid_merge"
    #: Joining: both sides hold the file, with no common base.
    JOIN_DIFFERS = "join_differs"


class StopKind(StrEnum):
    CONFLICTS = "conflicts"
    HOLD = "hold"


class HoldDirection(StrEnum):
    #: What the other machine's changes would delete here.
    INCOMING = "incoming"
    #: What this machine's own commits would delete on the remote.
    OUTGOING = "outgoing"


@dataclasses.dataclass(frozen=True)
class ConflictFile:
    path: str
    area: str
    reason: ConflictReason
    #: The blob on this machine / the other side / the merge base (``None``:
    #: absent on that side).
    ours: str | None
    theirs: str | None
    base: str | None = None
    #: When each side last changed the file (ISO time of the newest commit
    #: touching it), and which machine made the other side's change.
    ours_time: str | None = None
    theirs_time: str | None = None
    theirs_machine: str | None = None
    #: For a same-name conflict: the other path involved.
    other_path: str | None = None
    answer: Answer | None = None
    #: The blob of the person's hand-merged version (``answer == edited``).
    edited: str | None = None

    def answered(self, answer: Answer, edited: str | None = None) -> ConflictFile:
        return dataclasses.replace(self, answer=answer, edited=edited)

    @property
    def chosen_blob(self) -> str | None:
        """The blob the answer puts at ``path`` (``None`` deletes it)."""
        if self.answer is Answer.MINE:
            return self.ours
        if self.answer is Answer.THEIRS:
            return self.theirs
        if self.answer is Answer.EDITED:
            return self.edited
        raise ValueError(f"{self.path} has no answer yet")


@dataclasses.dataclass(frozen=True)
class Hold:
    direction: HoldDirection
    breaches: tuple[Breach, ...]
    #: Every path the round would lose, for the review list.
    paths: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class Stop:
    kind: StopKind
    local: str
    remote: str
    base: str | None
    raised_at: str
    conflicts: tuple[ConflictFile, ...] = ()
    hold: Hold | None = None
    #: The merged tree git produced (with conflict markers where it could
    #: not merge); answers are applied on top of it.
    tree: str | None = None
    #: When joining with a base recovered from this machine's descriptor.
    join: str | None = None

    @property
    def unanswered(self) -> tuple[ConflictFile, ...]:
        return tuple(c for c in self.conflicts if c.answer is None)

    def with_answer(self, path: str, answer: Answer, edited: str | None = None) -> Stop:
        found = False
        out: list[ConflictFile] = []
        for c in self.conflicts:
            if c.path == path:
                found = True
                out.append(c.answered(answer, edited))
            else:
                out.append(c)
        if not found:
            raise KeyError(path)
        return dataclasses.replace(self, conflicts=tuple(out))


def to_json(value: Any) -> Any:
    """A stop (or any part of one) as plain JSON."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_json(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, tuple | list):
        return [to_json(v) for v in value]
    if isinstance(value, StrEnum):
        return value.value
    return value


def conflict_from_json(raw: dict[str, Any]) -> ConflictFile:
    return ConflictFile(
        path=raw["path"],
        area=raw["area"],
        reason=ConflictReason(raw["reason"]),
        ours=raw.get("ours"),
        theirs=raw.get("theirs"),
        base=raw.get("base"),
        ours_time=raw.get("ours_time"),
        theirs_time=raw.get("theirs_time"),
        theirs_machine=raw.get("theirs_machine"),
        other_path=raw.get("other_path"),
        answer=Answer(raw["answer"]) if raw.get("answer") else None,
        edited=raw.get("edited"),
    )


def stop_from_json(raw: dict[str, Any]) -> Stop:
    hold = raw.get("hold")
    return Stop(
        kind=StopKind(raw["kind"]),
        local=raw["local"],
        remote=raw["remote"],
        base=raw.get("base"),
        raised_at=raw["raised_at"],
        conflicts=tuple(conflict_from_json(c) for c in raw.get("conflicts") or ()),
        hold=Hold(
            direction=HoldDirection(hold["direction"]),
            breaches=tuple(Breach(**b) for b in hold["breaches"]),
            paths=tuple(hold["paths"]),
        )
        if hold
        else None,
        tree=raw.get("tree"),
        join=raw.get("join"),
    )


__all__ = [
    "Answer",
    "Breach",
    "ConflictFile",
    "ConflictReason",
    "Hold",
    "HoldDirection",
    "Stop",
    "StopKind",
    "conflict_from_json",
    "stop_from_json",
    "to_json",
]
