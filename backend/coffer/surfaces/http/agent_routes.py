"""/api/v1/agents/* — agent registry HTTP routes (spec 004)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field

from coffer.application.agent.auto_detect import AutoDetectService
from coffer.application.agent.service import AgentService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.types import AgentType
from coffer.domain.resource import Resource
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor as _actor
from coffer.surfaces.http.dependencies import get_agent_service, get_auto_detect_service

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"],
    dependencies=[Depends(require_token)],
)


class AgentCreate(BaseModel):
    type: AgentType
    # Pattern aligned with `Resource.name` rules: short identifier composed of
    # alphanumerics, underscores, and hyphens (no slashes — names appear in
    # URL paths and must not introduce route ambiguity).
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    skill_dir: str | None = None
    description: str | None = None


class AgentPatch(BaseModel):
    skill_dir: str | None = None
    description: str | None = None
    enabled: bool | None = None


class AgentOut(BaseModel):
    name: str
    type: AgentType
    skill_dir: str
    skill_dir_override: str | None
    auto_detected: bool
    enabled: bool
    description: str | None
    created_at: datetime
    updated_at: datetime


class AgentListOut(BaseModel):
    items: list[AgentOut]


class AgentDetectOut(BaseModel):
    registered: list[AgentOut]


def _to_out(r: Resource) -> AgentOut:
    cfg = AgentConfig.model_validate(r.config)
    return AgentOut(
        name=r.name,
        type=cfg.type,
        skill_dir=str(cfg.resolved_skill_dir()),
        skill_dir_override=cfg.skill_dir,
        auto_detected=cfg.auto_detected,
        enabled=r.enabled,
        description=r.description,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


@router.get("", response_model=AgentListOut)
async def list_agents(
    svc: AgentService = Depends(get_agent_service),  # noqa: B008
) -> AgentListOut:
    items = await svc.list()
    return AgentListOut(items=[_to_out(r) for r in items])


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
async def register_agent(
    body: AgentCreate,
    svc: AgentService = Depends(get_agent_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> AgentOut:
    r = await svc.register(
        agent_type=body.type,
        name=body.name,
        skill_dir=body.skill_dir,
        description=body.description,
        actor=actor,
        auto_detected=False,
    )
    return _to_out(r)


@router.get("/{name}", response_model=AgentOut)
async def get_agent(
    name: str,
    svc: AgentService = Depends(get_agent_service),  # noqa: B008
) -> AgentOut:
    return _to_out(await svc.get(name))


@router.patch("/{name}", response_model=AgentOut)
async def update_agent(
    name: str,
    body: AgentPatch,
    svc: AgentService = Depends(get_agent_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> AgentOut:
    # `model_fields_set` distinguishes "field absent from the PATCH body"
    # from "field explicitly set to null". A PATCH that omits `skill_dir`
    # must preserve any existing override, not reset it to the default.
    sent = body.model_fields_set
    r = await svc.get(name)
    if "skill_dir" in sent or "description" in sent:
        current = AgentConfig.model_validate(r.config)
        r = await svc.update_skill_dir(
            name=name,
            new_skill_dir=body.skill_dir if "skill_dir" in sent else current.skill_dir,
            actor=actor,
            description=body.description if "description" in sent else r.description,
        )
    if body.enabled is not None and body.enabled != r.enabled:
        r = await svc.set_enabled(name=name, enabled=body.enabled, actor=actor)
    return _to_out(r)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_agent(
    name: str,
    svc: AgentService = Depends(get_agent_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> Response:
    await svc.remove(name=name, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/detect", response_model=AgentDetectOut)
async def detect_agents(
    svc: AutoDetectService = Depends(get_auto_detect_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> AgentDetectOut:
    registered = await svc.run_once(actor=actor)
    return AgentDetectOut(registered=[_to_out(r) for r in registered])
