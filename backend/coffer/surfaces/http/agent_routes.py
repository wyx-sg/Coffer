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
    # Optional. When omitted the server derives a stable default from the type
    # (mirrors auto-detect naming, e.g. claude_code -> claude-code). When a
    # name IS supplied it must follow `Resource.name` rules: a short identifier
    # of alphanumerics, underscores, and hyphens (no slashes — names appear in
    # URL paths and must not introduce route ambiguity).
    name: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    skill_dir: str | None = None
    description: str | None = None


class AgentPatch(BaseModel):
    # FR-006: agents have no enable/disable concept — only skill_dir and
    # description are updatable. (No `enabled` field by design.)
    skill_dir: str | None = None
    description: str | None = None


class AgentOut(BaseModel):
    name: str
    type: AgentType
    # Root config directory for the type (~/.claude, ~/.codex) — where the
    # agent's config files live. Derived from the type, not stored.
    config_dir: str
    skill_dir: str
    skill_dir_override: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime


class AgentListOut(BaseModel):
    items: list[AgentOut]


class AgentCandidate(BaseModel):
    """An installed-but-unregistered agent the user may choose to add."""

    type: AgentType
    display_name: str
    config_dir: str
    default_skill_dir: str
    suggested_name: str


class AgentCandidatesOut(BaseModel):
    candidates: list[AgentCandidate]


def _to_out(r: Resource) -> AgentOut:
    cfg = AgentConfig.model_validate(r.config)
    return AgentOut(
        name=r.name,
        type=cfg.type,
        config_dir=str(cfg.type.config_dir()),
        skill_dir=str(cfg.resolved_skill_dir()),
        skill_dir_override=cfg.skill_dir,
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
        name=body.name or body.type.default_name(),
        skill_dir=body.skill_dir,
        description=body.description,
        actor=actor,
    )
    return _to_out(r)


# Declared before GET /{name} so "candidates" isn't captured as an agent name.
@router.get("/candidates", response_model=AgentCandidatesOut)
async def list_candidates(
    svc: AutoDetectService = Depends(get_auto_detect_service),  # noqa: B008
) -> AgentCandidatesOut:
    """Discover installed agents that aren't registered yet (read-only).

    The user reviews these and chooses which to add — nothing is registered
    automatically (discovery + confirm).
    """
    found = await svc.discover()
    return AgentCandidatesOut(
        candidates=[
            AgentCandidate(
                type=c.type,
                display_name=c.display_name,
                config_dir=c.config_dir,
                default_skill_dir=c.default_skill_dir,
                suggested_name=c.suggested_name,
            )
            for c in found
        ]
    )


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
    return _to_out(r)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_agent(
    name: str,
    svc: AgentService = Depends(get_agent_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> Response:
    await svc.remove(name=name, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
