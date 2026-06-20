"""/api/v1/skills/{name}/* — content-trust endpoints.

Split out of ``skill_routes.py`` (component size cap): the scan / acknowledge
(trust layer L2, FR-028/FR-029) endpoints plus their wire schemas. Shares the
skill name/actor guards and the SkillOut mapper with the main skills router.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from coffer.application.skill.scan_ops import acknowledge_risk, rescan_skill
from coffer.application.skill.service import SkillService
from coffer.domain.skill.content_scan import ScanReport
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_skill_service
from coffer.surfaces.http.skill_routes import (
    SkillOut,
    _actor,
    _agents_by_id,
    _to_skill_out,
    _validate_skill_name,
)

router = APIRouter(
    prefix="/api/v1/skills",
    tags=["skills"],
    dependencies=[Depends(require_token)],
)


# ---------- schemas ----------


class ScanFindingOut(BaseModel):
    severity: str
    rule_id: str
    file: str
    line: int
    message: str


class ScanReportOut(BaseModel):
    verdict: str | None
    findings: list[ScanFindingOut]
    ruleset_version: str
    truncated: bool
    requires_acknowledgment: bool


def _to_scan_report_out(report: ScanReport) -> ScanReportOut:
    return ScanReportOut(
        verdict=report.verdict.value if report.verdict is not None else None,
        findings=[
            ScanFindingOut(
                severity=f.severity.value,
                rule_id=f.rule_id,
                file=f.file,
                line=f.line,
                message=f.message,
            )
            for f in report.findings
        ],
        ruleset_version=report.ruleset_version,
        truncated=report.truncated,
        requires_acknowledgment=report.requires_acknowledgment,
    )


# ---------- routes ----------


@router.post("/{name}/scan", response_model=ScanReportOut)
async def scan_skill(
    name: str,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ScanReportOut:
    name = _validate_skill_name(name)
    report = await rescan_skill(service=svc, name=name, actor=actor)
    return _to_scan_report_out(report)


@router.post("/{name}/acknowledge-risk", response_model=SkillOut)
async def acknowledge_skill_risk(
    name: str,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> SkillOut:
    name = _validate_skill_name(name)
    r = await acknowledge_risk(service=svc, name=name, actor=actor)
    return await _to_skill_out(svc, r, await _agents_by_id(svc))
