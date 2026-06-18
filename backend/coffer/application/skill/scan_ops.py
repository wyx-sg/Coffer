"""Content-scan + risk-acknowledgment helpers for SkillService (trust layer L2).

Free functions that take the SkillService instance and reach into its (private)
attributes — conceptually private to the skill subpackage, like ``update_ops``.
They translate between the pure ``domain.skill.content_scan`` report and the
persisted ``SkillConfig`` fields, and own the re-scan / acknowledge operations.
See spec 005 FR-028/FR-029 and ADR-026.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from coffer.domain.audit import AuditEventType
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.skill.config import SkillConfig
from coffer.domain.skill.content_scan import ScanReport, scan_skill_folder

if TYPE_CHECKING:
    from coffer.application.skill.service import SkillService


def scan_config_fields(report: ScanReport, *, scanned_at: datetime) -> dict[str, Any]:
    """The ``SkillConfig`` field updates derived from a scan report."""
    return {
        "scan_verdict": report.verdict.value if report.verdict is not None else None,
        "scan_findings_count": len(report.findings),
        "scan_ruleset_version": report.ruleset_version,
        "last_scanned_at": scanned_at,
    }


async def record_scan_audit(
    *, service: SkillService, name: str, report: ScanReport, actor: str
) -> None:
    """Record a SKILL_SCANNED audit row for a completed scan."""
    await service._audit.record(
        AuditEventType.SKILL_SCANNED.value,
        ref=ResourceRef("skill", name),
        actor=actor,
        details={
            "verdict": report.verdict.value if report.verdict is not None else None,
            "findings": len(report.findings),
            "ruleset_version": report.ruleset_version,
            "requires_acknowledgment": report.requires_acknowledgment,
        },
    )


async def rescan_skill(
    *, service: SkillService, name: str, actor: str, reset_acknowledgment: bool = False
) -> ScanReport:
    """Re-scan a managed skill's master folder, persist the verdict, audit.

    ``reset_acknowledgment`` is False for a manual re-scan of unchanged content
    (a re-scan must not silently revoke a prior acknowledgment) and True when
    the content just changed (an in-place file edit), where a prior
    acknowledgment was for the old content and must not carry over.
    """
    ref = ResourceRef("skill", name)
    resource = await service._rs.get(ref)
    cfg = SkillConfig.model_validate(resource.config)
    folder = service._store.paths_for(name).folder
    report = scan_skill_folder(folder)
    now = datetime.now(tz=UTC)
    update = scan_config_fields(report, scanned_at=now)
    if reset_acknowledgment:
        update["risk_acknowledged"] = False
    new_cfg = cfg.model_copy(update=update)
    await service._rs.update_config(
        ref,
        new_config=new_cfg.model_dump(mode="json"),
        actor=actor,
        allow_lifecycle_kind=True,  # CODE-REG: master folder unchanged; config-only
    )
    await record_scan_audit(service=service, name=name, report=report, actor=actor)
    return report


async def acknowledge_risk(*, service: SkillService, name: str, actor: str) -> Resource:
    """Mark a skill's scan risk as acknowledged so it may be enabled (FR-029)."""
    ref = ResourceRef("skill", name)
    resource = await service._rs.get(ref)
    cfg = SkillConfig.model_validate(resource.config)
    new_cfg = cfg.model_copy(update={"risk_acknowledged": True})
    updated = await service._rs.update_config(
        ref,
        new_config=new_cfg.model_dump(mode="json"),
        actor=actor,
        allow_lifecycle_kind=True,  # CODE-REG: master folder unchanged; config-only
    )
    await service._audit.record(
        AuditEventType.SKILL_RISK_ACKNOWLEDGED.value,
        ref=ref,
        actor=actor,
        details={"verdict": cfg.scan_verdict},
    )
    return updated
