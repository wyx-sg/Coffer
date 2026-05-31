"""Drift verification — extracted from `service.py` to respect file-size limits."""

from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING

from coffer.domain.audit import AuditEventType
from coffer.domain.skill.drift import DriftEntry, DriftKind, DriftReport, suggested_remedy

if TYPE_CHECKING:
    from coffer.application.skill.service import SkillService


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
