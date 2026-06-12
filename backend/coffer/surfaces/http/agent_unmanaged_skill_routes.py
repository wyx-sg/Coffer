"""/api/v1/agents/{name}/unmanaged-skills routes (spec 005 FR-022/023).

Unmanaged skills are skill-shaped folders discovered in an agent's workspace
that are not yet part of the Coffer master store. Routes here let the caller
list them, adopt them into the master store, or delete them from disk.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor as _actor
from coffer.surfaces.http.dependencies import get_skill_service

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
    name: str


# ---------- routes ----------


@router.get("/{name}/unmanaged-skills", response_model=UnmanagedListOut)
async def list_unmanaged_skills(
    name: str,
    svc: Any = Depends(get_skill_service),  # noqa: B008
) -> UnmanagedListOut:
    views = await svc.list_unmanaged(name)
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
    "/{name}/unmanaged-skills/{skill}/adopt",
    response_model=SkillRefOut,
    status_code=status.HTTP_201_CREATED,
)
async def adopt_unmanaged_skill(
    name: str,
    skill: str,
    body: AdoptBody,
    svc: Any = Depends(get_skill_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> SkillRefOut:
    resource = await svc.adopt_unmanaged(
        agent_name=name,
        skill_name=skill,
        location=body.location,
        actor=actor,
    )
    return SkillRefOut(name=resource.name)


@router.delete(
    "/{name}/unmanaged-skills/{skill}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_unmanaged_skill(
    name: str,
    skill: str,
    location: str,
    svc: Any = Depends(get_skill_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> Response:
    await svc.delete_unmanaged(
        agent_name=name,
        skill_name=skill,
        location=location,
        actor=actor,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
