"""/api/v1/agents/* — agent registry HTTP routes (spec 004)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field

from coffer.application.agent.auto_detect import AutoDetectService
from coffer.application.agent.service import AgentService
from coffer.domain.agent.capabilities import capabilities_for
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
    # Slice 6: opt-in native write-side memory disable. Toggling drives the
    # on-disk transform (Claude settings.json / Codex config.toml) in lockstep.
    disable_native_memory: bool | None = None
    # spec 011 amendment 2026-06-22b (E3): per-agent model binding. Explicit null
    # on `fast_model` clears the fast slot (distinguished via model_fields_set).
    model: str | None = None
    fast_model: str | None = None
    wire_api: str | None = None


class AgentCapabilitiesOut(BaseModel):
    """FR-003a capability-matrix slice: which optional facets this agent's type
    supports. Surfaces render a uniform "not supported" state for a false flag
    instead of an empty table or a raw error."""

    plugins: bool
    transcripts: bool
    connections: bool


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
    # Slice 6: whether the agent's native write-side memory is disabled.
    disable_native_memory: bool
    # spec 011 amendment 2026-06-22b (E3): per-agent model binding (None = unbound,
    # falls back to the active connection's model during rollout).
    model: str | None
    fast_model: str | None
    wire_api: str | None
    # FR-003a: per-type facet support, derived from the capability manifest.
    capabilities: AgentCapabilitiesOut
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
    caps = capabilities_for(cfg.type)
    return AgentOut(
        name=r.name,
        type=cfg.type,
        capabilities=AgentCapabilitiesOut(
            plugins=caps.plugins,
            transcripts=caps.transcripts,
            connections=caps.connections,
        ),
        config_dir=str(cfg.resolved_config_dir()),
        description=r.description,
        follow_all_skills=cfg.follow_all_skills,
        skill_exclusions=list(cfg.skill_exclusions),
        disable_native_memory=cfg.disable_native_memory,
        model=cfg.model,
        fast_model=cfg.fast_model,
        wire_api=cfg.wire_api,
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
    if "disable_native_memory" in sent and body.disable_native_memory is not None:
        # Drives the persisted field AND the on-disk native-memory transform in
        # lockstep (Claude settings.json / Codex config.toml).
        r = await svc.set_disable_native_memory(
            name=name, enabled=body.disable_native_memory, actor=actor
        )
    if "model" in sent or "fast_model" in sent or "wire_api" in sent:
        # Per-agent model binding (E3). An explicit null fast_model clears the
        # fast slot; the caller re-activates the connection to re-project.
        r = await svc.set_model_binding(
            name=name,
            model=body.model if "model" in sent else None,
            fast_model=body.fast_model if "fast_model" in sent else None,
            clear_fast_model="fast_model" in sent and body.fast_model is None,
            wire_api=body.wire_api if "wire_api" in sent else None,
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
