"""/api/v1/skills — an agent's copy in the way, and the store's orphan folders.

Spec skill-manager "Resolve a folder in the way of a skill's link" and "Act on
a folder in the skills store that no skill claims". Mounted before the main
skills router so ``GET /skills/orphans`` is not read as ``GET /skills/{uid}``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel

from coffer.application.skill import copy_ops, file_ops, orphan_ops
from coffer.application.skill.service import SkillService
from coffer.application.skill.source_service import SkillSourceService
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.skill_dependencies import (
    get_optional_skill_source_service,
    get_skill_service,
)
from coffer.surfaces.http.skill_file_routes import (
    SkillFileContentOut,
    SkillFileTreeOut,
    _content_out,
    _node_to_out,
)
from coffer.surfaces.http.skill_routes import SkillOut, _actor, _agents_by_uid, _to_skill_out
from coffer.surfaces.http.skill_source_schemas import SkillFileChangeOut, change_out

router = APIRouter(
    prefix="/api/v1/skills",
    tags=["skills"],
    dependencies=[Depends(require_token)],
)


class SkillCopyCompareOut(BaseModel):
    """One agent's folder in the way of the skill's link, against master."""

    skill_uid: str
    agent_uid: str
    agent_name: str
    #: The agent-side folder's absolute path.
    path: str
    kind: Literal["replaced_with_regular"]
    #: The newest file time in that folder, when it has files.
    modified_at: datetime | None
    #: From master to the agent's folder: what the agent's side has.
    changes: list[SkillFileChangeOut]


class SkillCopyResolveRequest(BaseModel):
    #: ``master`` puts Coffer's link back (the folder is backed up first);
    #: ``agent`` makes the folder's files the master, then links it.
    keep: Literal["master", "agent"]


class SkillOrphanOut(BaseModel):
    name: str
    path: str
    #: Its SKILL.md is valid and names the folder.
    valid: bool
    file_count: int
    description: str | None
    message: str | None
    #: When the folder last changed.
    found_at: datetime


class SkillOrphanListOut(BaseModel):
    items: list[SkillOrphanOut]


@router.get("/orphans", response_model=SkillOrphanListOut)
async def list_orphans(
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
) -> SkillOrphanListOut:
    return SkillOrphanListOut(
        items=[
            SkillOrphanOut(
                name=o.name,
                path=str(o.path),
                valid=o.valid,
                file_count=o.file_count,
                description=o.description,
                message=o.message,
                found_at=o.found_at,
            )
            for o in await orphan_ops.list_orphans(svc)
        ]
    )


@router.get("/orphans/{name}/files", response_model=SkillFileTreeOut)
async def list_orphan_files(
    name: str,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
) -> SkillFileTreeOut:
    """The orphan folder as a read-only file tree — the walk of a managed skill's."""
    folder = await orphan_ops.orphan_folder(svc, name)
    return SkillFileTreeOut(root=_node_to_out(file_ops.build_file_tree(folder), folder))


@router.get("/orphans/{name}/files/content", response_model=SkillFileContentOut)
async def read_orphan_file(
    name: str,
    path: str = Query(min_length=1),
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
) -> SkillFileContentOut:
    """Read one file of an orphan folder; a path outside it is refused with 400."""
    folder = await orphan_ops.orphan_folder(svc, name)
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


@router.post("/orphans/{name}/adopt", response_model=SkillOut, status_code=status.HTTP_201_CREATED)
async def adopt_orphan(
    name: str,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
    sources: SkillSourceService | None = Depends(get_optional_skill_source_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> SkillOut:
    skill = await orphan_ops.adopt_orphan(svc, name=name, actor=actor)
    return await _to_skill_out(svc, skill, await _agents_by_uid(svc), sources=sources)


@router.delete("/orphans/{name}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def remove_orphan(
    name: str,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> Response:
    await orphan_ops.remove_orphan(svc, name=name, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{uid}/copies/{agent_uid}", response_model=SkillCopyCompareOut)
async def compare_copy(
    uid: str,
    agent_uid: str,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
) -> SkillCopyCompareOut:
    c = await copy_ops.compare(svc, skill_uid=uid, agent_uid=agent_uid)
    return SkillCopyCompareOut(
        skill_uid=c.skill.uid,
        agent_uid=c.agent.uid,
        agent_name=c.agent.name,
        path=str(c.path),
        kind="replaced_with_regular",
        modified_at=c.modified_at,
        changes=[change_out(x) for x in c.changes],
    )


@router.post("/{uid}/copies/{agent_uid}/resolve", response_model=SkillOut)
async def resolve_copy(
    uid: str,
    agent_uid: str,
    body: SkillCopyResolveRequest,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
    sources: SkillSourceService | None = Depends(get_optional_skill_source_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> SkillOut:
    skill = await copy_ops.resolve(
        svc, skill_uid=uid, agent_uid=agent_uid, keep=body.keep, actor=actor
    )
    return await _to_skill_out(svc, skill, await _agents_by_uid(svc), sources=sources)
