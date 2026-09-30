"""The vocabulary of the unified reconciler — pure data and one pure diff.

ADR one-level-triggered-reconciler-compares-parameters. Everything Coffer keeps
true outside its own database (an MCP entry in an agent's config, a delivered
skill link, a provider projection, a delivery hook) is a *target*. A target
states what it wants as :class:`Item` values carrying their **full
parameters**, and observes what is there in the same shape. :func:`diff` pairs
the two by key and compares the parameters, so a changed argument is a
difference exactly as a missing entry is — the rule PR #413 taught (a hook
whose command kept an option the CLI had dropped read as "installed" for
months, because detection matched the marker and never read the arguments).

What a target may do about a difference is its own **direction policy**
(:class:`Decision`): repair it, only report it, or report that it cannot be
repaired right now. This module holds no policy and performs no I/O; the
application layer's reconciler runs the passes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal


class Op(StrEnum):
    """What a difference needs, read from the observed side's point of view."""

    #: Wanted, and not there.
    ADD = "add"
    #: There, with parameters other than the wanted ones.
    MODIFY = "modify"
    #: There, and not wanted.
    REMOVE = "remove"


class Disposition(StrEnum):
    """What the target's direction policy says about one difference."""

    #: The policy allows the write; a pass that is not a dry-run performs it.
    REPAIR = "repair"
    #: Reported only: repairing it by writing would act on evidence the
    #: policy does not accept (re-route a user's agent, clobber foreign content).
    REPORT = "report"
    #: Would be repaired, but cannot be right now (the launcher to point at is
    #: missing, the file does not parse). Reported until the cause is gone.
    BLOCKED = "blocked"


class Trigger(StrEnum):
    """Why a pass ran. Some direction policies read it: a difference may be
    repairable on the user's explicit request and only reportable otherwise."""

    #: The daemon starting.
    BOOT = "boot"
    #: The fixed period elapsing.
    PERIOD = "period"
    #: A ``Changed`` hint bringing the next pass forward.
    HINT = "hint"
    #: A kind asking for its own targets right after a write the user made
    #: (a skill's scope edited, an agent registered).
    CHANGE = "change"
    #: A sync import that just applied rows from another machine.
    IMPORT = "import"
    #: An experimental feature being switched.
    SWITCH = "switch"
    #: A person applying items from the drift view.
    MANUAL = "manual"


@dataclass(frozen=True)
class Subject:
    """The resource a difference is about, as a surface names it."""

    kind: str
    uid: str | None
    title: str


@dataclass(frozen=True)
class Item:
    """One thing a target wants, or finds, with its full parameters.

    ``key`` is stable within the target and pairs a desired item with its
    observed counterpart. ``params`` is what equality is judged on — every
    parameter, never presence alone. ``file`` names where the item lives;
    ``text`` is a rendering of the item that is safe to show a person (it
    never carries a secret value) and is what a change preview diffs.
    """

    key: str
    subject: Subject
    params: Mapping[str, Any]
    file: str | None = None
    text: str | None = None


@dataclass(frozen=True)
class Difference:
    """One key where what is wanted and what is there disagree."""

    target: str
    key: str
    op: Op
    desired: Item | None
    observed: Item | None

    @property
    def id(self) -> str:
        """The address a person applies this difference by."""
        return change_id(self.target, self.key)

    @property
    def subject(self) -> Subject:
        item = self.desired or self.observed
        assert item is not None  # a difference always has at least one side
        return item.subject

    @property
    def file(self) -> str | None:
        return (self.desired.file if self.desired else None) or (
            self.observed.file if self.observed else None
        )

    @property
    def changed_params(self) -> tuple[str, ...]:
        """The parameter names that differ, sorted — both sides' keys for a
        modification, the one side's for an addition or a removal."""
        before = dict(self.observed.params) if self.observed else {}
        after = dict(self.desired.params) if self.desired else {}
        names = set(before) | set(after)
        return tuple(sorted(n for n in names if before.get(n) != after.get(n)))


@dataclass(frozen=True)
class Decision:
    """A target's direction policy applied to one difference.

    ``reason_code`` is a stable machine code (``stale_command``,
    ``missing_launcher``); ``reason`` is one sentence a person can read.
    """

    disposition: Disposition
    reason_code: str
    reason: str
    #: The prompt that hands a difference no write settles to the person's
    #: agent (``domain/handoff.py``), when the target has one; the attention
    #: list carries it beside the item. ``None`` for everything a pass repairs.
    handoff: str | None = None


@dataclass(frozen=True)
class PlannedChange:
    difference: Difference
    decision: Decision

    @property
    def id(self) -> str:
        return self.difference.id


class Outcome(StrEnum):
    """What a pass did with one planned change."""

    #: Written, and its audit event recorded.
    APPLIED = "applied"
    #: The write, or the audit that must follow it, failed; nothing is left
    #: changed that the audit does not record, and the next pass retries it.
    FAILED = "failed"
    #: Not written: the policy reports it, it is blocked, or the pass was a
    #: dry-run.
    PLANNED = "planned"


@dataclass(frozen=True)
class ItemResult:
    change: PlannedChange
    outcome: Outcome
    error: str | None = None


@dataclass(frozen=True)
class TargetFailure:
    """A target that raised while being planned. The pass skipped it."""

    target: str
    error: str


@dataclass(frozen=True)
class PassReport:
    """Everything one pass found and did."""

    trigger: Trigger
    dry_run: bool
    started_at: datetime
    finished_at: datetime
    #: The targets the pass visited, in registration order.
    targets: tuple[str, ...]
    results: tuple[ItemResult, ...] = ()
    failures: tuple[TargetFailure, ...] = field(default_factory=tuple)

    def count(self, outcome: Outcome) -> int:
        return sum(1 for r in self.results if r.outcome is outcome)


#: What a write did to a resource row: it now exists with new content, or it
#: is gone.
ChangeOp = Literal["upsert", "delete"]


@dataclass(frozen=True)
class Changed:
    """An in-process hint that a resource was written.

    ``rev`` is the resource's monotonic revision after the write (a delete
    carries the row's last revision plus one); ``op`` says whether the row
    still exists. A hint only brings the next pass forward for the targets
    that follow ``kind``; losing one costs at most one period, never
    correctness, because every pass reads the whole state again. The daemon's
    event stream turns the same hint into an invalidation envelope.
    """

    kind: str
    uid: str
    rev: int
    op: ChangeOp = "upsert"


def change_id(target: str, key: str) -> str:
    """``<target>:<key>`` — unique across targets, because keys are unique
    within one."""
    return f"{target}:{key}"


def diff(target: str, desired: Sequence[Item], observed: Sequence[Item]) -> list[Difference]:
    """Pair ``desired`` and ``observed`` by key and compare their parameters.

    Desired keys come first in their own order, then observed-only keys in
    theirs, so a plan reads in the order the target states it. Equal
    parameters are no difference; unequal ones are a modification even when
    the item "is there" by every presence test.

    Raises ``ValueError`` on a key a side states twice: two items under one
    key would make the pairing ambiguous, and that is a target bug.
    """
    wanted = _by_key(target, desired, "desired")
    found = _by_key(target, observed, "observed")
    out: list[Difference] = []
    for key, want in wanted.items():
        have = found.get(key)
        if have is None:
            out.append(Difference(target, key, Op.ADD, want, None))
        elif dict(have.params) != dict(want.params):
            out.append(Difference(target, key, Op.MODIFY, want, have))
    for key, have in found.items():
        if key not in wanted:
            out.append(Difference(target, key, Op.REMOVE, None, have))
    return out


def _by_key(target: str, items: Sequence[Item], side: str) -> dict[str, Item]:
    out: dict[str, Item] = {}
    for item in items:
        if item.key in out:
            raise ValueError(f"target {target!r} states {side} key {item.key!r} twice")
        out[item.key] = item
    return out


__all__ = [
    "ChangeOp",
    "Changed",
    "Decision",
    "Difference",
    "Disposition",
    "Item",
    "ItemResult",
    "Op",
    "Outcome",
    "PassReport",
    "PlannedChange",
    "Subject",
    "TargetFailure",
    "Trigger",
    "change_id",
    "diff",
]
