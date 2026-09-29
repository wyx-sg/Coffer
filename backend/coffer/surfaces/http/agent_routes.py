"""/api/v1/agents/* — agent registry HTTP routes (spec agent-registry).

There is one agent per type, named by it, so every ``{uid}`` below also takes
the type (``claude-code`` or ``claude_code``): ``resolve_agent_path`` turns it
into the uid before the handler runs.
"""

from __future__ import annotations

import pathlib
from datetime import datetime

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from coffer.application.agent.auto_detect import AgentTypeDetection, AutoDetectService
from coffer.application.agent.service import AgentService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.detection import DetectionState
from coffer.domain.agent.types import AgentType
from coffer.domain.resource import Resource
from coffer.surfaces.http.agent_dependencies import (
    get_agent_service,
    get_auto_detect_service,
)
from coffer.surfaces.http.agent_type_path import resolve_agent_path
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor as _actor

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"],
    dependencies=[Depends(require_token), Depends(resolve_agent_path)],
)


class AgentCreate(BaseModel):
    # There is one agent per type and it is named by the type (spec
    # agent-registry "Keep one agent per type, named by it"): the type is the
    # whole of what registration asks for, beside an optional directory.
    type: AgentType
    # Optional override of the agent's config directory. When omitted the server
    # uses the type's standard location (~/.claude, ~/.codex). Skills are
    # delivered to <config_dir>/skills.
    config_dir: str | None = None


class AgentPatch(BaseModel):
    # Only config_dir and the model binding are updatable here. The agent's
    # `enabled` flag is the kind-agnostic one, toggled through
    # POST /resources/{uid}/enable|disable (spec agent-registry "Switch an agent
    # off with the kind-agnostic enabled flag"). Which skills reach this agent
    # is decided on each skill resource (`enabled` + `scope`), never here.
    config_dir: str | None = None
    # spec provider-switching "Take projected model keys from the agent's binding":
    # per-agent model binding. Explicit null
    # on `fast_model` clears the fast slot (distinguished via model_fields_set).
    model: str | None = None
    fast_model: str | None = None
    wire_api: str | None = None


class AgentOut(BaseModel):
    # The agent's identity (ADR resource-identity-is-an-immutable-uid). Every
    # route here also takes the type in its place, because there is one agent
    # per type.
    uid: str
    #: The type's name (``claude-code``, ``codex``) — fixed, and the same on
    #: every surface; there is no title or description beside it.
    name: str
    #: The product's name for people ("Claude Code", "OpenAI Codex").
    display_name: str
    type: AgentType
    # The agent's config directory — where its config files live and, under
    # <config_dir>/skills, where Coffer delivers skills. Either the user's
    # override or the type's standard location (~/.claude, ~/.codex).
    config_dir: str
    # spec provider-switching "Take projected model keys from the agent's binding": per-agent model
    # binding. ``None`` = unbound, and unbound means unbound — the connection
    # carries no singular model to fall back to, so projection writes no model
    # for this agent at all.
    model: str | None
    fast_model: str | None
    wire_api: str | None
    # Two-signal detection (spec agent-registry "Detect an agent by its
    # program and its config directory"): the program on the agent's real
    # PATH, and the config directory on disk. Read at request time.
    state: DetectionState
    # The version the agent's program reports, when it was found and answered.
    version: str | None
    created_at: datetime
    updated_at: datetime


class AgentListOut(BaseModel):
    items: list[AgentOut]


class AgentTypeOut(BaseModel):
    """One supported type, registered or not — a row the Agents page always
    renders (spec agent-registry "Report every supported type's detection
    state")."""

    type: AgentType
    #: The name its one agent carries (``claude-code``, ``codex``).
    name: str
    display_name: str
    #: The registered agent's directory, or the one Add would register.
    config_dir: str
    #: The type's standard directory — where Add registers without another.
    standard_config_dir: str
    default_skill_dir: str
    # ``installed_active`` (addable), ``installed_never_run`` (addable:
    # registration creates the standard directory), ``config_only`` (the
    # program is not installed: not addable) or ``missing``.
    state: DetectionState
    version: str | None
    #: The registered agent of this type; ``None`` when it is not added.
    uid: str | None
    #: Whether Add may register it now.
    addable: bool
    #: Another directory seen for this type (the one its environment variable
    #: names), offered as "use a different config directory".
    other_config_dir: str | None


class AgentTypesOut(BaseModel):
    types: list[AgentTypeOut]


class AgentCandidatesOut(BaseModel):
    """The supported types seen here and not registered yet — at most one per type."""

    candidates: list[AgentTypeOut]


def _type_out(row: AgentTypeDetection) -> AgentTypeOut:
    return AgentTypeOut(
        type=row.type,
        name=row.name,
        display_name=row.display_name,
        config_dir=row.config_dir,
        standard_config_dir=row.standard_config_dir,
        default_skill_dir=row.default_skill_dir,
        state=row.state,
        version=row.version,
        uid=row.uid,
        addable=row.addable,
        other_config_dir=row.other_config_dir,
    )


async def _to_out(r: Resource, detect: AutoDetectService) -> AgentOut:
    cfg = AgentConfig.model_validate(r.config)
    detection = await detect.detect(cfg.type, cfg.resolved_config_dir())
    return AgentOut(
        uid=r.uid,
        name=r.name,
        display_name=cfg.type.display_name,
        type=cfg.type,
        config_dir=str(cfg.resolved_config_dir()),
        model=cfg.model,
        fast_model=cfg.fast_model,
        wire_api=cfg.wire_api,
        state=detection.state,
        version=detection.version,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


@router.get("", response_model=AgentListOut)
async def list_agents(
    svc: AgentService = Depends(get_agent_service),  # noqa: B008
    detect: AutoDetectService = Depends(get_auto_detect_service),  # noqa: B008
) -> AgentListOut:
    items = await svc.list()
    return AgentListOut(items=[await _to_out(r, detect) for r in items])


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
async def register_agent(
    body: AgentCreate,
    svc: AgentService = Depends(get_agent_service),  # noqa: B008
    detect: AutoDetectService = Depends(get_auto_detect_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> AgentOut:
    """Register the one agent of ``type``, named by it.

    An agent installed but never run here (``installed_never_run``) has no
    config directory yet; registering it at its standard location creates that
    directory with only what Coffer needs (spec agent-registry "Validate the
    config directory at registration"). Any other missing directory is refused.
    """
    standard = body.type.config_dir()
    wanted = pathlib.Path(body.config_dir).expanduser() if body.config_dir else standard
    create = False
    if wanted.is_absolute() and wanted == standard:
        create = (await detect.detect(body.type, standard)).state is (
            DetectionState.INSTALLED_NEVER_RUN
        )
    r = await svc.register(
        agent_type=body.type,
        config_dir=body.config_dir,
        create_config_dir=create,
        actor=actor,
    )
    return await _to_out(r, detect)


# Declared before GET /{uid} so neither path is captured as an agent.
@router.get("/types", response_model=AgentTypesOut)
async def list_types(
    svc: AutoDetectService = Depends(get_auto_detect_service),  # noqa: B008
) -> AgentTypesOut:
    """Every supported type with its detection state, registered or not
    (read-only), so a surface can always show one row per type."""
    return AgentTypesOut(types=[_type_out(row) for row in await svc.types()])


@router.get("/candidates", response_model=AgentCandidatesOut)
async def list_candidates(
    svc: AutoDetectService = Depends(get_auto_detect_service),  # noqa: B008
) -> AgentCandidatesOut:
    """The supported types seen on this machine that aren't registered yet
    (read-only), each with its detection state and version (spec agent-registry
    "Detect an agent by its program and its config directory"). Nothing is
    registered automatically (discovery + confirm).
    """
    return AgentCandidatesOut(candidates=[_type_out(row) for row in await svc.discover()])


@router.get("/{uid}", response_model=AgentOut)
async def get_agent(
    uid: str,
    svc: AgentService = Depends(get_agent_service),  # noqa: B008
    detect: AutoDetectService = Depends(get_auto_detect_service),  # noqa: B008
) -> AgentOut:
    return await _to_out(await svc.get(uid), detect)


@router.patch("/{uid}", response_model=AgentOut)
async def update_agent(
    uid: str,
    body: AgentPatch,
    svc: AgentService = Depends(get_agent_service),  # noqa: B008
    detect: AutoDetectService = Depends(get_auto_detect_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> AgentOut:
    # `model_fields_set` distinguishes "field absent from the PATCH body"
    # from "field explicitly set to null". A PATCH that omits `config_dir`
    # must preserve any existing override, not reset it to the default.
    sent = body.model_fields_set
    r = await svc.get(uid)
    if "config_dir" in sent:
        r = await svc.update_config_dir(uid=uid, new_config_dir=body.config_dir, actor=actor)
    if "model" in sent or "fast_model" in sent or "wire_api" in sent:
        # Per-agent model binding. An explicit null fast_model clears the
        # fast slot; the caller re-activates the connection to re-project.
        r = await svc.set_model_binding(
            uid=uid,
            model=body.model if "model" in sent else None,
            fast_model=body.fast_model if "fast_model" in sent else None,
            clear_fast_model="fast_model" in sent and body.fast_model is None,
            wire_api=body.wire_api if "wire_api" in sent else None,
            actor=actor,
        )
    return await _to_out(r, detect)


@router.delete("/{uid}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_agent(
    uid: str,
    svc: AgentService = Depends(get_agent_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> Response:
    await svc.remove(uid=uid, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
