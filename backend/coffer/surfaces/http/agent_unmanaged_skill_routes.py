"""/api/v1/agents/{uid}/unmanaged-skills routes (spec skill-manager FR-016/023).

Unmanaged skills are skill-shaped folders discovered in an agent's workspace
that are not yet part of the Coffer master store. Routes here let the caller
list them, adopt them into the master store, or delete them from disk.

The agent is addressed by ``{uid}`` like everywhere else, but ``{skill}`` is a
DIRECTORY name and stays one: an unmanaged folder has no resource row, so there
is no uid to name it by (ADR resource-identity-is-an-immutable-uid). Adoption is
the moment one is minted, which is why its response carries the new uid.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor as _actor
from coffer.surfaces.http.skill_dependencies import get_skill_service

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"],
    dependencies=[Depends(require_token)],
)


# ---------- response / request schemas ----------


class UnmanagedSkillOut(BaseModel):
    name: str
    path: str
    location: str  # "skills" | "agents_dir"
    valid: bool
    reason: str | None
    foreign_link: bool


class UnmanagedListOut(BaseModel):
    items: list[UnmanagedSkillOut]


class AdoptBody(BaseModel):
    location: str


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
    resource = await svc.adopt_unmanaged(
        agent_uid=uid,
        skill_name=skill,
        location=body.location,
        actor=actor,
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
    location: str,
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
