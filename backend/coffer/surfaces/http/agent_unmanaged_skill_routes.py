"""/api/v1/agents/{uid}/unmanaged-skills routes.

Spec skill-manager "List unmanaged skills in an agent's skill locations" and
"Expose unmanaged-skill operations under the skill surfaces".

Unmanaged skills are skill-shaped folders discovered in an agent's workspace
that are not yet part of the Coffer master store. Routes here let the caller
list them, preview one read-only (its SKILL.md metadata, file tree and file
contents), adopt them into the master store, or delete them from disk.

The agent is addressed by ``{uid}`` like everywhere else, but ``{skill}`` is a
DIRECTORY name and stays one: an unmanaged folder has no resource row, so there
is no uid to name it by (ADR identity-is-the-uid-inside-the-file). Adoption is
the moment one is minted, which is why its response carries the new uid.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel

from coffer.application.skill import file_ops
from coffer.surfaces.http.agent_type_path import resolve_agent_path
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor as _actor
from coffer.surfaces.http.skill_dependencies import get_skill_service
from coffer.surfaces.http.skill_file_routes import (
    SkillFileContentOut,
    SkillFileTreeOut,
    _content_out,
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


class UnmanagedSkillDetailOut(UnmanagedSkillOut):
    """One unmanaged skill for its read-only detail page.

    ``description`` is the SKILL.md frontmatter's, known only when the folder
    validates; an invalid folder carries ``reason`` instead.
    """

    description: str | None


class AdoptBody(BaseModel):
    location: Location


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


@router.get("/{uid}/unmanaged-skills/{skill}", response_model=UnmanagedSkillDetailOut)
async def get_unmanaged_skill(
    uid: str,
    skill: str,
    location: Location,
    svc: Any = Depends(get_skill_service),  # noqa: B008
) -> UnmanagedSkillDetailOut:
    """One unmanaged skill's metadata (spec skill-manager "Preview an unmanaged
    skill read-only"). 404 when the scan finds no such entry at ``location``."""
    detail = await svc.get_unmanaged(agent_uid=uid, skill_name=skill, location=location)
    v = detail.view
    return UnmanagedSkillDetailOut(
        name=v.name,
        path=v.path,
        location=v.location,
        valid=v.valid,
        reason=v.reason,
        foreign_link=v.foreign_link,
        description=detail.description,
    )


@router.get("/{uid}/unmanaged-skills/{skill}/files", response_model=SkillFileTreeOut)
async def list_unmanaged_skill_files(
    uid: str,
    skill: str,
    location: Location,
    svc: Any = Depends(get_skill_service),  # noqa: B008
) -> SkillFileTreeOut:
    """The unmanaged folder as a read-only file tree — the same walk, and the
    same containment, as a managed skill's master folder."""
    detail = await svc.get_unmanaged(agent_uid=uid, skill_name=skill, location=location)
    folder = detail.folder.resolve()
    return SkillFileTreeOut(root=_node_to_out(file_ops.build_file_tree(folder), folder))


@router.get("/{uid}/unmanaged-skills/{skill}/files/content", response_model=SkillFileContentOut)
async def read_unmanaged_skill_file(
    uid: str,
    skill: str,
    location: Location,
    path: str = Query(min_length=1),
    svc: Any = Depends(get_skill_service),  # noqa: B008
) -> SkillFileContentOut:
    """Read one file of an unmanaged folder. A path resolving outside the
    folder (``..``, absolute, escaping symlink) is refused with 400 before
    anything is read; there is no write counterpart."""
    detail = await svc.get_unmanaged(agent_uid=uid, skill_name=skill, location=location)
    folder = detail.folder.resolve()
    try:
        result = file_ops.read_skill_file(folder, path)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="requested path is outside the skill folder",
        ) from exc
    except (FileNotFoundError, IsADirectoryError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no such file in skill: {path}",
        ) from exc
    return _content_out(result, folder)


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
