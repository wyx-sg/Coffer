"""/api/v1/agents/{uid}/unmanaged-skills routes.

Spec skill-manager "List unmanaged skills in an agent's skill locations" and
"Expose unmanaged-skill operations under the skill surfaces".

Unmanaged skills are skill-shaped folders discovered in an agent's workspace
that are not yet part of the Coffer master store. Routes here let the caller
list them, list one's file tree (for the Adopt and Delete dialogs), adopt
them into the master store, or delete them from disk.

The agent is addressed by ``{uid}`` like everywhere else, but ``{skill}`` is a
DIRECTORY name and stays one: an unmanaged folder has no resource row, so there
is no uid to name it by (ADR identity-is-the-uid-inside-the-file). Adoption is
the moment one is minted, which is why its response carries the new uid.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field

from coffer.application.skill import file_ops
from coffer.domain.scope import Scope
from coffer.surfaces.http.agent_type_path import resolve_agent_path
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor as _actor
from coffer.surfaces.http.skill_dependencies import get_skill_service
from coffer.surfaces.http.skill_file_routes import (
    SkillFileTreeOut,
    _node_to_out,
)

Location = Literal["skills", "agents_dir"]

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"],
    dependencies=[Depends(require_token), Depends(resolve_agent_path)],
)


# ---------- response / request schemas ----------


class UnmanagedSkillOut(BaseModel):
    name: str
    path: str
    location: Location
    valid: bool
    reason: str | None
    foreign_link: bool


class UnmanagedListOut(BaseModel):
    items: list[UnmanagedSkillOut]


class AdoptReach(BaseModel):
    """Who gets the adopted skill: every agent, only the listed agents, or
    nobody (the skill is adopted switched off)."""

    mode: Literal["everywhere", "restricted", "disabled"] = "everywhere"
    #: Agent uids; read only when ``mode`` is ``restricted``.
    agents: list[str] = Field(default_factory=list)


class AdoptBody(BaseModel):
    location: Location
    #: The skill's name in Coffer; absent keeps the SKILL.md front matter's name.
    name: str | None = Field(default=None, min_length=1)
    reach: AdoptReach | None = None


class SkillRefOut(BaseModel):
    """The managed skill an adoption just created.

    The ``uid`` is what a caller needs to go on and address the new skill —
    ``/api/v1/skills/{uid}`` — while the ``name`` is what it tells the user was
    adopted. An unmanaged folder had neither: it has no resource row at all,
    which is why it is named by its directory name in the path above.
    """

    uid: str
    name: str


# ---------- routes ----------


@router.get("/{uid}/unmanaged-skills", response_model=UnmanagedListOut)
async def list_unmanaged_skills(
    uid: str,
    svc: Any = Depends(get_skill_service),  # noqa: B008
) -> UnmanagedListOut:
    views = await svc.list_unmanaged(uid)
    return UnmanagedListOut(
        items=[
            UnmanagedSkillOut(
                name=v.name,
                path=v.path,
                location=v.location,
                valid=v.valid,
                reason=v.reason,
                foreign_link=v.foreign_link,
            )
            for v in views
        ]
    )


@router.get("/{uid}/unmanaged-skills/{skill}/files", response_model=SkillFileTreeOut)
async def list_unmanaged_skill_files(
    uid: str,
    skill: str,
    location: Location,
    svc: Any = Depends(get_skill_service),  # noqa: B008
) -> SkillFileTreeOut:
    """The unmanaged folder's file tree, which the Adopt and Delete dialogs
    list — the same walk, and the same containment, as a managed skill's
    master folder. Coffer reads no file of it."""
    detail = await svc.get_unmanaged(agent_uid=uid, skill_name=skill, location=location)
    folder = detail.folder.resolve()
    return SkillFileTreeOut(root=_node_to_out(file_ops.build_file_tree(folder), folder))


@router.post(
    "/{uid}/unmanaged-skills/{skill}/adopt",
    response_model=SkillRefOut,
    status_code=status.HTTP_201_CREATED,
)
async def adopt_unmanaged_skill(
    uid: str,
    skill: str,
    body: AdoptBody,
    svc: Any = Depends(get_skill_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> SkillRefOut:
    reach = body.reach
    resource = await svc.adopt_unmanaged(
        agent_uid=uid,
        skill_name=skill,
        location=body.location,
        actor=actor,
        name=body.name,
        enabled=reach is None or reach.mode != "disabled",
        scope=Scope(agents=reach.agents)
        if reach is not None and reach.mode == "restricted"
        else None,
    )
    return SkillRefOut(uid=resource.uid, name=resource.name)


@router.delete(
    "/{uid}/unmanaged-skills/{skill}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_unmanaged_skill(
    uid: str,
    skill: str,
    location: Location,
    svc: Any = Depends(get_skill_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> Response:
    await svc.delete_unmanaged(
        agent_uid=uid,
        skill_name=skill,
        location=location,
        actor=actor,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
