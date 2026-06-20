"""Drift verification — extracted from `service.py` to respect file-size limits."""

from __future__ import annotations

import logging
import pathlib
from typing import TYPE_CHECKING

from coffer.domain.audit import AuditEventType
from coffer.domain.error_base import CofferError
from coffer.domain.resource import ResourceRef
from coffer.domain.skill.drift import (
    DriftEntry,
    DriftKind,
    DriftReport,
    RepairResult,
    suggested_remedy,
)

if TYPE_CHECKING:
    from coffer.application.skill.service import SkillService

logger = logging.getLogger(__name__)


async def verify_drift(service: SkillService) -> DriftReport:
    """Walk every enabled binding + check the on-disk state."""
    report = DriftReport()
    skills = await service._rs.list(kind="skill")
    agents = await service._rs.list(kind="agent")
    by_skill_id = {s.id: s for s in skills}
    by_agent_id = {a.id: a for a in agents}

    for b in await service._bindings.list_enabled():
        skill = by_skill_id.get(b.skill_resource_id)
        agent = by_agent_id.get(b.agent_resource_id)
        if skill is None or agent is None:
            continue
        expected_master = service._store.paths_for(skill.name).folder
        link_path = pathlib.Path(
            b.last_link_path or str(service._resolve_agent_skill_dir(agent) / skill.name)
        )
        status = service._sync.classify_target(
            link=link_path,
            expected_master=expected_master,
            link_mode=b.link_mode,
        )
        if status.drift is not None:
            report.entries.append(
                DriftEntry(
                    skill_name=skill.name,
                    agent_name=agent.name,
                    kind=status.drift,
                    target_path=status.target_path,
                    suggested_remedy=suggested_remedy(status.drift),
                )
            )

    known = {s.name for s in skills}
    for orphan in service._store.find_orphans(known):
        report.entries.append(
            DriftEntry(
                skill_name=orphan,
                agent_name="",
                kind=DriftKind.ORPHAN_MASTER,
                target_path=str(service._store.paths_for(orphan).folder),
                suggested_remedy=suggested_remedy(DriftKind.ORPHAN_MASTER),
            )
        )

    if report.has_drift:
        await service._audit.record(
            AuditEventType.SKILL_DRIFT_DETECTED.value,
            ref=None,
            actor="system",
            details={
                "count": len(report.entries),
                "kinds": [e.kind.value for e in report.entries],
            },
        )
    return report


# Drift kinds that are safe to auto-repair by re-delivering from master.
# REPLACED_WITH_REGULAR, MISSING_MASTER, and ORPHAN_MASTER are intentionally
# skipped: we never clobber foreign content and cannot re-deliver from a
# missing master.
_REPAIRABLE_KINDS = frozenset(
    {
        DriftKind.MISSING_LINK,
        DriftKind.TAMPERED_LINK,
    }
)


async def repair_drift(service: SkillService, *, actor: str) -> RepairResult:
    """Opt-in repair: re-deliver safely-repairable drift kinds from master.

    Repairable kinds
    ----------------
    MISSING_LINK      — link is gone; re-enable with force=False recreates it.
    TAMPERED_LINK     — link points elsewhere; force=True backs it up + re-links.

    Skipped kinds (left in ``remaining``)
    ----------------------------------------
    REPLACED_WITH_REGULAR — a foreign regular dir occupies the path; never clobber.
    MISSING_MASTER        — master is gone; nothing to re-deliver.
    ORPHAN_MASTER         — no binding row; out of scope for binding repair.

    Returns
    -------
    RepairResult with ``remediated`` (successfully re-delivered entries) and
    ``remaining`` (residual DriftReport from a second verify pass after repair).
    """
    initial = await verify_drift(service)
    remediated: list[DriftEntry] = []

    for entry in initial.entries:
        if entry.kind not in _REPAIRABLE_KINDS:
            continue
        force = entry.kind is DriftKind.TAMPERED_LINK
        try:
            await service.enable_for(
                skill_name=entry.skill_name,
                agent_name=entry.agent_name,
                force=force,
                actor=actor,
            )
        except (CofferError, OSError):
            logger.warning(
                "repair_drift: could not repair %s/%s (%s)",
                entry.skill_name,
                entry.agent_name,
                entry.kind.value,
                exc_info=True,
            )
            continue
        remediated.append(entry)
        await service._audit.record(
            AuditEventType.SKILL_DRIFT_REMEDIATED.value,
            ref=ResourceRef("skill", entry.skill_name),
            actor=actor,
            details={
                "agent": entry.agent_name,
                "kind": entry.kind.value,
            },
        )

    residual = await verify_drift(service)
    return RepairResult(remediated=remediated, remaining=residual)
