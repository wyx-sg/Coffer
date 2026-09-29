"""``coffer skill verify`` and ``verify --fix``, read from the reconciler.

The drift report and the repair result keep their wire shape
(``DriftReport`` / ``RepairResult``), but neither computes anything of its
own any more: verify is the ``skill_link`` target's dry-run plan, and repair
applies the repairable items of that plan through the reconciler — the same
writes, the same audit, the same direction policy as every other pass
(ADR one-level-triggered-reconciler-compares-parameters).

The report keeps its old meaning: a delivery that was made (a binding row
records it) and no longer holds on disk, plus master folders no row claims. A
delivery still to be made is a pending change, not drift, and a path the
policy would not touch because Coffer never delivered there is not drift
either.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import TYPE_CHECKING, Protocol

from coffer.application.skill.link_reconcile import (
    AGENT_DIR_MISSING,
    OK,
    ORPHAN_PREFIX,
    TARGET,
    split_key,
)
from coffer.domain.errors import CofferError
from coffer.domain.reconcile import Disposition, Outcome, PassReport, PlannedChange
from coffer.domain.skill.drift import (
    DriftEntry,
    DriftKind,
    DriftReport,
    RepairResult,
    suggested_remedy,
)

if TYPE_CHECKING:
    from coffer.application.skill.service import SkillService


class _Reconciler(Protocol):
    async def plan(self, *, targets: Collection[str] | None = ...) -> PassReport: ...

    async def apply(self, change_ids: Collection[str], *, actor: str) -> PassReport: ...


#: An agent whose config dir is gone still has a missing link; the policy just
#: will not create the dir to put one back.
_KIND_OF_STATE = {AGENT_DIR_MISSING: DriftKind.MISSING_LINK}


async def _entry(service: SkillService, change: PlannedChange) -> DriftEntry | None:
    d = change.difference
    observed = d.observed
    if d.target != TARGET or observed is None:
        return None
    state = str(observed.params["state"])
    if d.key.startswith(ORPHAN_PREFIX):
        kind = DriftKind.ORPHAN_MASTER
        return DriftEntry(
            # A folder no row claims: there is no uid on either side, and the
            # name is a directory name, not a label Coffer issued.
            skill_name=d.key.removeprefix(ORPHAN_PREFIX),
            agent_name="",
            kind=kind,
            target_path=str(observed.params["target"]),
            suggested_remedy=suggested_remedy(kind),
        )
    if state == OK or not observed.params.get("bound"):
        return None
    kind = _KIND_OF_STATE.get(state) or DriftKind(state)
    skill_uid, agent_uid = split_key(d.key)
    try:
        skill = await service._rs.get(skill_uid)
        agent = await service._rs.get(agent_uid)
    except CofferError:
        return None
    return DriftEntry(
        skill_name=skill.name,
        agent_name=agent.name,
        kind=kind,
        target_path=str(observed.params["link"]),
        suggested_remedy=suggested_remedy(kind),
        skill_uid=skill.uid,
        agent_uid=agent.uid,
    )


async def _entries(
    service: SkillService, plan: PassReport
) -> list[tuple[PlannedChange, DriftEntry]]:
    out: list[tuple[PlannedChange, DriftEntry]] = []
    for result in plan.results:
        entry = await _entry(service, result.change)
        if entry is not None:
            out.append((result.change, entry))
    return out


async def drift_report(service: SkillService, plan: PassReport) -> DriftReport:
    """The drift entries a ``skill_link`` plan holds."""
    return DriftReport(entries=[e for _c, e in await _entries(service, plan)])


async def verify(service: SkillService, reconciler: _Reconciler) -> DriftReport:
    return await drift_report(service, await reconciler.plan(targets=[TARGET]))


async def repair(service: SkillService, reconciler: _Reconciler, *, actor: str) -> RepairResult:
    """Apply every drift entry the policy repairs (missing and tampered links;
    never foreign content, a missing master or an orphan), then verify again."""
    pairs = await _entries(service, await reconciler.plan(targets=[TARGET]))
    wanted = {c.id: e for c, e in pairs if c.decision.disposition is Disposition.REPAIR}
    remediated: list[DriftEntry] = []
    if wanted:
        report = await reconciler.apply(list(wanted), actor=actor)
        remediated = [
            wanted[r.change.id]
            for r in report.results
            if r.outcome is Outcome.APPLIED and r.change.id in wanted
        ]
    return RepairResult(remediated=remediated, remaining=await verify(service, reconciler))


__all__ = ["drift_report", "repair", "verify"]
