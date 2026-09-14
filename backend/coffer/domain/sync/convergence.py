"""What one converge round reports (spec vault-sync ``## The converge round``).

Pure value objects. A round does not raise for anything the user can be told
about — it returns a :class:`ConvergeRun` carrying the status — so the worker's
loop never has to decide what is survivable.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import StrEnum

from coffer.domain.sync.diff import DiffSummary


class JoinKind(StrEnum):
    """How a machine with no pointer met the remote.

    The distinction is load-bearing, not descriptive. A machine the remote has
    never seen takes the union and cannot delete anything, because its base is
    the empty tree. A machine the remote *has* seen — one that lost its pointer
    to a reinstall — must recover its base from its own published descriptor:
    treated as new it would republish everything the other machines deleted
    while it was away, with no conflict raised, because a union has no base to
    disagree with.
    """

    NEW = "new"
    RETURNING = "returning"


class ConvergeStatus(StrEnum):
    OK = "ok"
    #: Nothing to do on either side. A success, not a skip.
    NO_CHANGE = "no_change"
    #: git could not merge and nothing resolved it. The vault is untouched and
    #: the pointer has not moved; the user resolves in their own git.
    CONFLICT = "conflict"
    #: The deletion guard tripped. Held, with what it would remove, until the
    #: user confirms or rejects.
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    #: Everything applied locally; the push did not land. The commit stays and
    #: the next round carries it, exactly as a backup push failure always did.
    PUSH_FAILED = "push_failed"
    FAILED = "failed"
    DISABLED = "disabled"


class GuardDirection(StrEnum):
    """Which way the deletion guard tripped.

    ``APPLY`` means the remote would delete too much of this vault. ``PUBLISH``
    means this vault would delete too much of the remote — the case where this
    machine is the damaged one, and the one that stops a reinstall or a stray
    ``rm -rf`` from taking every other machine down with it.
    """

    APPLY = "apply"
    PUBLISH = "publish"


@dataclasses.dataclass(frozen=True, slots=True)
class PendingConfirmation:
    """A round held at the guard, and everything needed to resume it."""

    direction: GuardDirection
    #: The commit the round had reached. Resuming applies from here; rejecting
    #: resets the working tree back to the pointer.
    commit: str
    #: The remote tip this hold was raised against. A confirmation is an
    #: answer about a specific diff, so if the remote moved in the meantime the
    #: round must re-derive and ask again rather than apply the user's "yes" to
    #: something they were never shown.
    remote_tip: str | None
    #: ``(area, deleted, total)`` per breached area.
    breaches: tuple[tuple[str, int, int], ...]
    paths: tuple[str, ...]
    raised_at: datetime


@dataclasses.dataclass(frozen=True, slots=True)
class ConvergeRun:
    """The outcome of one round."""

    status: ConvergeStatus
    started_at: datetime
    finished_at: datetime
    join: JoinKind | None = None
    #: What the round applied to this vault.
    applied: DiffSummary = dataclasses.field(default_factory=DiffSummary)
    #: What the round published to the remote.
    published: DiffSummary = dataclasses.field(default_factory=DiffSummary)
    commit: str | None = None
    #: Paths git could not merge and nothing resolved.
    conflicts: tuple[str, ...] = ()
    #: Paths an agent resolved, reported whether or not the round succeeded —
    #: a silent machine merge of the user's own notes is the thing they would
    #: most want to know happened.
    agent_resolved: tuple[str, ...] = ()
    #: ``(path, reason)`` for documents that could not be applied here.
    failures: tuple[tuple[str, str], ...] = ()
    #: Credential refs whose ciphertext will not decrypt on this machine.
    locked_refs: tuple[str, ...] = ()
    pending: PendingConfirmation | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in (ConvergeStatus.OK, ConvergeStatus.NO_CHANGE)


@dataclasses.dataclass(frozen=True, slots=True)
class RunRecord:
    """One round as the history keeps it.

    A round on its own carries no identity — two rounds that changed nothing
    are equal values — so the history pairs it with the id it was stored
    under. That id is what a surface keys a row on; it is never shown.
    """

    id: int
    run: ConvergeRun
