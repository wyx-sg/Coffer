"""/api/v1/skills/* — skill manager HTTP routes (spec 005-skill-manager)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, Field

from coffer.application.skill.service import SkillService
from coffer.domain.resource import Resource
from coffer.domain.skill.binding import BindingState, LinkMode
from coffer.domain.skill.config import SkillConfig
from coffer.domain.skill.content_scan import verdict_requires_ack
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_skill_service

router = APIRouter(
    prefix="/api/v1/skills",
    tags=["skills"],
    dependencies=[Depends(require_token)],
)


# ---------- request schemas ----------


class SkillImportRequest(BaseModel):
    path: str = Field(min_length=1)


class SkillEnableRequest(BaseModel):
    agent_name: str = Field(min_length=1)
    force: bool = False


class SkillDisableRequest(BaseModel):
    agent_name: str = Field(min_length=1)


# ---------- response schemas ----------


class SkillBindingOut(BaseModel):
    agent_name: str
    enabled: bool
    last_linked_at: datetime | None = None
    last_link_path: str | None = None
    link_mode: LinkMode | None = None


class SkillOut(BaseModel):
    name: str
    description: str
    source: dict[str, Any]
    enabled: bool
    version_hash: str
    master_path: str
    last_synced_from_source_at: datetime | None
    created_at: datetime
    updated_at: datetime
    bindings: list[SkillBindingOut]
    # Trust layer L2 (FR-028/FR-029).
    scan_verdict: str | None = None
    scan_findings_count: int = 0
    last_scanned_at: datetime | None = None
    risk_acknowledged: bool = False
    # True when the verdict gates enabling and the risk is not yet acknowledged.
    requires_acknowledgment: bool = False


class SkillListOut(BaseModel):
    items: list[SkillOut]


class DriftEntryOut(BaseModel):
    skill_name: str
    agent_name: str
    kind: str
    target_path: str
    suggested_remedy: str


class DriftReportOut(BaseModel):
    entries: list[DriftEntryOut]


# The skill master-folder viewer/editor schemas + routes live in
# ``skill_file_routes.py`` (split out for the component size cap).


# ---------- helpers ----------


def _actor(x_coffer_actor: str | None = Header(default=None)) -> str:
    return x_coffer_actor or "api"


# Skill names appear in URL path segments and become on-disk folder names
# under ``~/.coffer/skills/<name>/`` via ``MasterStore.paths_for``. The same
# regex as ``ResourceRef`` (``^[a-zA-Z0-9_.\-]+$``, ≤64 chars) is enforced
# at the surface to catch path-traversal attempts (``..``, ``/``, ``\``)
# and reject them with 422 BEFORE the value reaches the filesystem layer.
_SKILL_NAME_RE = re.compile(r"^[a-zA-Z0-9_.\-]+$")
_SKILL_NAME_MAX = 64


def _validate_skill_name(name: str) -> str:
    if not name or len(name) > _SKILL_NAME_MAX or not _SKILL_NAME_RE.match(name):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "INVALID_NAME",
                    "message": (
                        f"invalid skill name: must match {_SKILL_NAME_RE.pattern} "
                        f"and be ≤{_SKILL_NAME_MAX} chars"
                    ),
                }
            },
        )
    return name


async def _agents_by_id(svc: SkillService) -> dict[int, str]:
    """Build an agent-id -> name map once per request (avoids an N+1)."""
    return {a.id: a.name for a in await svc.list_agents()}


async def _to_skill_out(
    svc: SkillService,
    r: Resource,
    agents_by_id: dict[int, str],
    *,
    bindings_by_skill: dict[int, list[BindingState]] | None = None,
) -> SkillOut:
    cfg = SkillConfig.model_validate(r.config)
    # Single-skill handlers (get / import / fetch / update / enable / disable)
    # take the per-skill round-trip — list handlers prebuild the map once
    # via ``svc.bindings_grouped_by_skill()`` to collapse N queries into 1.
    if bindings_by_skill is not None:
        bindings = bindings_by_skill.get(r.id, [])
    else:
        bindings = await svc.bindings_for(r.name)
    return SkillOut(
        name=r.name,
        description=cfg.skill_md_description,
        source=cfg.source.model_dump(mode="json"),
        enabled=r.enabled,
        version_hash=cfg.version_hash,
        master_path=svc.master_path(r.name),
        last_synced_from_source_at=cfg.last_synced_from_source_at,
        created_at=r.created_at,
        updated_at=r.updated_at,
        scan_verdict=cfg.scan_verdict,
        scan_findings_count=cfg.scan_findings_count,
        last_scanned_at=cfg.last_scanned_at,
        risk_acknowledged=cfg.risk_acknowledged,
        requires_acknowledgment=(
            verdict_requires_ack(cfg.scan_verdict) and not cfg.risk_acknowledged
        ),
        bindings=[
            SkillBindingOut(
                agent_name=agents_by_id.get(b.agent_resource_id, str(b.agent_resource_id)),
                enabled=b.enabled,
                last_linked_at=b.last_linked_at,
                last_link_path=b.last_link_path,
                link_mode=b.link_mode,
            )
            for b in bindings
        ],
    )


# ---------- routes ----------


@router.get("", response_model=SkillListOut)
async def list_skills(
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
) -> SkillListOut:
    rs = await svc.list_skills()
    agents_by_id = await _agents_by_id(svc)
    # Prebuild the binding lookup once — collapses what was a 2N+2 query
    # pattern (one ``list_for_skill`` + one ``get`` per skill) into ~3.
    bindings_by_skill = await svc.bindings_grouped_by_skill()
    items = [
        await _to_skill_out(svc, r, agents_by_id, bindings_by_skill=bindings_by_skill) for r in rs
    ]
    return SkillListOut(items=items)


@router.post("/import", response_model=SkillOut, status_code=status.HTTP_201_CREATED)
async def import_skill(
    body: SkillImportRequest,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> SkillOut:
    r = await svc.import_local(path=body.path, actor=actor)
    return await _to_skill_out(svc, r, await _agents_by_id(svc))


@router.get("/{name}", response_model=SkillOut)
async def get_skill(
    name: str,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
) -> SkillOut:
    name = _validate_skill_name(name)
    r = await svc.get_skill(name)
    return await _to_skill_out(svc, r, await _agents_by_id(svc))


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_skill(
    name: str,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> Response:
    name = _validate_skill_name(name)
    await svc.remove(name=name, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{name}/enable", response_model=SkillBindingOut)
async def enable_skill_for_agent(
    name: str,
    body: SkillEnableRequest,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> SkillBindingOut:
    name = _validate_skill_name(name)
    b = await svc.enable_for(
        skill_name=name,
        agent_name=body.agent_name,
        force=body.force,
        actor=actor,
    )
    return SkillBindingOut(
        agent_name=body.agent_name,
        enabled=b.enabled,
        last_linked_at=b.last_linked_at,
        last_link_path=b.last_link_path,
        link_mode=b.link_mode,
    )


@router.post("/{name}/disable", response_model=SkillBindingOut)
async def disable_skill_for_agent(
    name: str,
    body: SkillDisableRequest,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> SkillBindingOut:
    name = _validate_skill_name(name)
    b = await svc.disable_for(skill_name=name, agent_name=body.agent_name, actor=actor)
    return SkillBindingOut(
        agent_name=body.agent_name,
        enabled=b.enabled,
        last_linked_at=b.last_linked_at,
        last_link_path=b.last_link_path,
        link_mode=b.link_mode,
    )


@router.post("/verify", response_model=DriftReportOut)
async def verify_skills(
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
) -> DriftReportOut:
    report = await svc.verify()
    return DriftReportOut(
        entries=[
            DriftEntryOut(
                skill_name=e.skill_name,
                agent_name=e.agent_name,
                kind=e.kind.value,
                target_path=e.target_path,
                suggested_remedy=e.suggested_remedy,
            )
            for e in report.entries
        ]
    )


# Trust-layer (scan / acknowledge) endpoints live in
# ``skill_trust_routes.py`` (component size cap).
