"""/api/v1/agents/* — agent registry HTTP routes (spec 004)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field

from coffer.application.agent.auto_detect import AutoDetectService
from coffer.application.agent.native_memory import scan_claude_native_memory
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
    # Optional override of the agent's config directory. When omitted the server
    # uses the type's standard location (~/.claude, ~/.codex). Skills are
    # delivered to <config_dir>/skills.
    config_dir: str | None = None
    description: str | None = None


class AgentPatch(BaseModel):
    # FR-006: agents have no enable/disable concept — only config_dir,
    # description, and follow policy are updatable. (No `enabled` field by design.)
    config_dir: str | None = None
    description: str | None = None
    # FR-025: follow-master-library policy fields.
    follow_all_skills: bool | None = None
    skill_exclusions: list[str] | None = None


class AgentOut(BaseModel):
    name: str
    type: AgentType
    # The agent's config directory — where its config files live and, under
    # <config_dir>/skills, where Coffer delivers skills. Either the user's
    # override or the type's standard location (~/.claude, ~/.codex).
    config_dir: str
    description: str | None
    # FR-025: follow-master-library policy fields.
    follow_all_skills: bool
    skill_exclusions: list[str]
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


class NativeMemoryProjectOut(BaseModel):
    """One project's native memory directory under the agent's config dir."""

    slug: str
    memory_dir: str
    fact_count: int
    managed: bool


class NativeMemoryOut(BaseModel):
    projects: list[NativeMemoryProjectOut]
    #: Facts across projects not yet managed by Coffer (a quick banner number).
    unmanaged_fact_count: int


def _to_out(r: Resource) -> AgentOut:
    cfg = AgentConfig.model_validate(r.config)
    return AgentOut(
        name=r.name,
        type=cfg.type,
        config_dir=str(cfg.resolved_config_dir()),
        description=r.description,
        follow_all_skills=cfg.follow_all_skills,
        skill_exclusions=list(cfg.skill_exclusions),
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
        config_dir=body.config_dir,
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


@router.get("/{name}/native-memory", response_model=NativeMemoryOut)
async def get_native_memory(
    name: str,
    svc: AgentService = Depends(get_agent_service),  # noqa: B008
) -> NativeMemoryOut:
    """Discover the agent's EXISTING on-disk memory (read-only). Surfaces memory
    Claude Code wrote natively that Coffer hasn't taken over yet."""
    r = await svc.get(name)
    cfg = AgentConfig.model_validate(r.config)
    if cfg.type is not AgentType.CLAUDE_CODE:
        return NativeMemoryOut(projects=[], unmanaged_fact_count=0)
    found = scan_claude_native_memory(cfg.resolved_config_dir())
    return NativeMemoryOut(
        projects=[
            NativeMemoryProjectOut(
                slug=p.slug,
                memory_dir=p.memory_dir,
                fact_count=p.fact_count,
                managed=p.managed,
            )
            for p in found
        ],
        unmanaged_fact_count=sum(p.fact_count for p in found if not p.managed),
    )


@router.patch("/{name}", response_model=AgentOut)
async def update_agent(
    name: str,
    body: AgentPatch,
    svc: AgentService = Depends(get_agent_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> AgentOut:
    # `model_fields_set` distinguishes "field absent from the PATCH body"
    # from "field explicitly set to null". A PATCH that omits `config_dir`
    # must preserve any existing override, not reset it to the default.
    sent = body.model_fields_set
    r = await svc.get(name)
    if "config_dir" in sent or "description" in sent:
        current = AgentConfig.model_validate(r.config)
        r = await svc.update_config_dir(
            name=name,
            new_config_dir=body.config_dir if "config_dir" in sent else current.config_dir,
            actor=actor,
            description=body.description if "description" in sent else r.description,
        )
    if "follow_all_skills" in sent or "skill_exclusions" in sent:
        r = await svc.update_skill_policy(
            name=name,
            follow_all_skills=body.follow_all_skills if "follow_all_skills" in sent else None,
            skill_exclusions=body.skill_exclusions if "skill_exclusions" in sent else None,
            actor=actor,
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
