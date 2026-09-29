"""The contract a reconcile target implements, and what its writes hand back.

A target is supplied by a kind or an agent facet and registered with the
:class:`~coffer.application.reconcile.reconciler.Reconciler` at the
composition root. It has four parts:

- :meth:`ReconcileTarget.desired` — computed only from Coffer's own state, as
  items carrying their full parameters;
- :meth:`ReconcileTarget.observe` — what is actually there, parsed into the
  same shape;
- :meth:`ReconcileTarget.decide` — the direction policy, turning each
  difference into repair / report / blocked, given why the pass runs;
- :meth:`ReconcileTarget.apply` — the one write a repairable difference
  needs, through the kind's own marker-scoped, atomic, backed-up writer.

``apply`` performs the write and returns what the reconciler must record: the
audit event, and how to restore what was there if recording it fails. It does
not record the event itself — the reconciler does, in the same call, so every
target follows one audit rule ("audit follows the write").
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from coffer.domain.reconcile import Decision, Difference, Item, PlannedChange, Trigger
from coffer.domain.resource import Resource

#: Restores what a write replaced — the prior content its backup holds. Called
#: only when the audit event for that write could not be recorded.
Undo = Callable[[], Awaitable[None]]


@dataclass(frozen=True)
class AuditEvent:
    """One audit row a repair must leave behind."""

    event_type: str
    resource: Resource | None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Applied:
    """What a target's write hands back.

    ``event`` is ``None`` only for a repair whose write already went through a
    service that audits it in the database itself (a flag Coffer corrects in
    its own record), where there is no outside file to restore.
    """

    event: AuditEvent | None
    undo: Undo | None = None


class ReconcileTarget(Protocol):
    """One thing Coffer keeps true outside its database."""

    @property
    def name(self) -> str:
        """Stable, and the first half of every change id this target plans."""
        ...

    @property
    def kinds(self) -> frozenset[str]:
        """The resource kinds whose ``Changed`` hint brings this target's next
        pass forward."""
        ...

    async def desired(self) -> Sequence[Item]: ...

    async def observe(self) -> Sequence[Item]: ...

    def decide(self, differences: Sequence[Difference], trigger: Trigger) -> Sequence[Decision]:
        """One decision per difference, in the same order. Given all of them
        at once, because a policy may depend on the rest of the plan."""
        ...

    async def apply(self, change: PlannedChange) -> Applied:
        """Perform the write for one repairable change. Raises to report it
        as failed; the reconciler never retries within a pass."""
        ...


__all__ = ["Applied", "AuditEvent", "ReconcileTarget", "Undo"]
