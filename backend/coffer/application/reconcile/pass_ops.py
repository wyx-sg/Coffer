"""One pass's two steps for one target, split out of ``reconciler.py``.

:func:`plan_target` asks the target what it wants and what is there, diffs the
two including parameters and lets its direction policy decide each
difference. :func:`settle_change` performs one planned change: a dry-run or a
difference the policy will not repair is only planned; a repair is written by
the target and its audit event recorded in the same call, and when recording
fails the target's undo restores what the write replaced and the item fails.
"""

from __future__ import annotations

import logging

from coffer.application.audit_service import AuditService
from coffer.application.reconcile.ports import ReconcileTarget
from coffer.domain.reconcile import (
    Disposition,
    ItemResult,
    Outcome,
    PassReport,
    PlannedChange,
    Trigger,
    diff,
)

_log = logging.getLogger("coffer.application.reconcile.reconciler")

#: The actor recorded on a repair, by what caused the pass. A person applying
#: from the drift view is recorded as themselves (the caller's actor).
ACTORS: dict[Trigger, str] = {
    Trigger.BOOT: "system",
    Trigger.PERIOD: "system",
    Trigger.HINT: "system",
    Trigger.CHANGE: "system",
    Trigger.IMPORT: "sync",
    Trigger.SWITCH: "system:features",
    Trigger.MANUAL: "api",
}


async def plan_target(target: ReconcileTarget, trigger: Trigger) -> list[PlannedChange]:
    desired = await target.desired()
    observed = await target.observe()
    differences = diff(target.name, desired, observed)
    decisions = list(target.decide(differences, trigger))
    if len(decisions) != len(differences):
        raise ValueError(f"target {target.name!r} decided {len(decisions)} of {len(differences)}")
    return [PlannedChange(d, dec) for d, dec in zip(differences, decisions, strict=True)]


async def settle_change(
    audit: AuditService,
    target: ReconcileTarget,
    change: PlannedChange,
    trigger: Trigger,
    *,
    dry_run: bool,
    actor: str | None,
) -> ItemResult:
    if dry_run or change.decision.disposition is not Disposition.REPAIR:
        return ItemResult(change, Outcome.PLANNED)
    try:
        applied = await target.apply(change)
    except Exception as exc:
        _log.warning("reconcile.apply_failed %s: %r", change.id, exc)
        return ItemResult(change, Outcome.FAILED, repr(exc))
    if applied.event is None:
        return ItemResult(change, Outcome.APPLIED)
    event = applied.event
    try:
        await audit.record(
            event.event_type,
            resource=event.resource,
            actor=actor or ACTORS[trigger],
            # Why the reconciler wrote: the decision's reason code (unless the
            # target named one itself) and the trigger of the pass.
            details={
                "reason": change.decision.reason_code,
                **event.details,
                "reconcile": trigger.value,
            },
        )
    except Exception as exc:
        _log.error("reconcile.audit_failed %s: %r", change.id, exc)
        if applied.undo is not None:
            try:
                await applied.undo()
            except Exception:
                # The write stands unaudited; the daemon log is the record.
                _log.exception("reconcile.undo_failed %s", change.id)
        return ItemResult(change, Outcome.FAILED, f"audit not recorded: {exc!r}")
    return ItemResult(change, Outcome.APPLIED)


def log_report(report: PassReport) -> None:
    """One log line per repair, failure and reported difference."""
    for r in report.results:
        if r.outcome is Outcome.APPLIED:
            _log.info("reconcile.applied %s (%s)", r.change.id, r.change.decision.reason_code)
        elif r.outcome is Outcome.FAILED:
            _log.warning("reconcile.failed %s: %s", r.change.id, r.error)
        elif r.change.decision.disposition is not Disposition.REPAIR:
            _log.info("reconcile.reported %s: %s", r.change.id, r.change.decision.reason)


__all__ = ["ACTORS", "log_report", "plan_target", "settle_change"]
