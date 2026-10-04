"""Reconciler drift as an attention source.

Every difference a fresh dry-run plan still holds is something Coffer says and
the agent's own files do not. A repairable one is offered as "repair" — the
same apply route the drift view calls; a blocked one (the launcher is missing,
foreign content sits where a link belongs) is offered as "review", because no
write would help until its cause is gone. The plan is computed on every read
and writes nothing; "since" is when a writing pass first saw it. A repairable
difference no writing pass has visited yet is left out — the next pass repairs
it on its own — so the list holds what a pass could not fix. A difference
whose target hands it to an agent (a folder in the way of a skill's link) carries
that prompt as the item's hand-off.
"""

from __future__ import annotations

from collections.abc import Sequence

from coffer.application.attention import AttentionAction, AttentionItem, Severity
from coffer.application.reconcile.reconciler import Reconciler
from coffer.domain.reconcile import Disposition, PlannedChange, Trigger

APPLY_PATH = "/api/v1/reconcile/apply"
PLAN_PATH = "/api/v1/reconcile/plan"


def _action(change: PlannedChange, manual: PlannedChange | None) -> AttentionAction:
    """Repair when a person applying it would get a write; otherwise review."""
    repairable = manual is not None and manual.decision.disposition is Disposition.REPAIR
    if repairable:
        return AttentionAction("repair", "POST", APPLY_PATH, {"ids": [change.id]})
    return AttentionAction("review", "GET", f"{PLAN_PATH}?target={change.difference.target}")


def _severity(change: PlannedChange) -> Severity:
    return (
        Severity.ERROR if change.decision.disposition is Disposition.BLOCKED else Severity.WARNING
    )


class DriftAttentionSource:
    """Implements ``AttentionSource`` over the reconciler's plan."""

    name = "reconcile"
    feature: str | None = None

    def __init__(self, reconciler: Reconciler) -> None:
        self._reconciler = reconciler

    async def items(self) -> Sequence[AttentionItem]:
        # What a periodic pass would do, and what a person's apply would do:
        # the first says what is open, the second whether "repair" is honest.
        periodic = await self._reconciler.plan(trigger=Trigger.PERIOD)
        manual = await self._reconciler.plan(trigger=Trigger.MANUAL)
        by_id = {r.change.id: r.change for r in manual.results}
        out: list[AttentionItem] = []
        for result in periodic.results:
            change = result.change
            since = self._reconciler.first_seen(change.id)
            if change.decision.disposition is Disposition.REPAIR and since is None:
                # New drift no writing pass has visited: the next pass repairs
                # it without anyone. Only a repair that a pass already tried
                # and that is still open needs a person.
                continue
            subject = change.difference.subject
            out.append(
                AttentionItem(
                    kind=subject.kind,
                    uid=subject.uid,
                    title=subject.title,
                    reason_code=change.decision.reason_code,
                    reason=change.decision.reason,
                    severity=_severity(change),
                    action=_action(change, by_id.get(change.id)),
                    since=since,
                    handoff=change.decision.handoff,
                )
            )
        for failure in periodic.failures:
            out.append(
                AttentionItem(
                    kind="reconcile",
                    uid=None,
                    title=failure.target,
                    reason_code="target_failed",
                    reason=f"Coffer could not check {failure.target}: {failure.error}",
                    severity=Severity.ERROR,
                    action=AttentionAction("review", "GET", f"{PLAN_PATH}?target={failure.target}"),
                )
            )
        return out


__all__ = ["APPLY_PATH", "PLAN_PATH", "DriftAttentionSource"]
