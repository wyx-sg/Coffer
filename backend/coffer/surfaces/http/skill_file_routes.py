"""/api/v1/skills/{name}/files* — skill master-folder viewer + editor.

Split out of ``skill_routes.py`` (component size cap): the file-tree, single-file
read, and single-file write endpoints plus their wire schemas. Shares the skill
name/actor guards with the main skills router.
"""

from __future__ import annotations

import pathlib

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from coffer.application.skill import content_ops, file_ops
from coffer.application.skill.service import SkillService
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_skill_service
from coffer.surfaces.http.skill_routes import _actor, _validate_skill_name

router = APIRouter(
    prefix="/api/v1/skills",
    tags=["skills"],
    dependencies=[Depends(require_token)],
)


# ---------- schemas ----------


class SkillFileNodeOut(BaseModel):
    name: str
    path: str  # POSIX, relative to the master folder root ("" for the root)
    type: str  # "file" | "dir"
    size: int | None = None
    truncated: bool = False  # directory clipped at the max walk depth
    children: list[SkillFileNodeOut] = Field(default_factory=list)


class SkillFileTreeOut(BaseModel):
    root: SkillFileNodeOut


class SkillFileContentOut(BaseModel):
    path: str  # POSIX, relative to the master folder root
    content: str  # empty when ``binary`` is true
    truncated: bool
    binary: bool
    size: int


class SkillFileWriteRequest(BaseModel):
    path: str = Field(min_length=1)  # POSIX, relative to the master folder root
    content: str  # full new file contents (UTF-8)


# ---------- helpers ----------


def _node_to_out(node: file_ops.FileNode) -> SkillFileNodeOut:
    return SkillFileNodeOut(
        name=node.name,
        path=node.path,
        type=node.type,
        size=node.size,
        truncated=node.truncated,
        children=[_node_to_out(c) for c in node.children],
    )


def _content_out(result: file_ops.FileContent) -> SkillFileContentOut:
    return SkillFileContentOut(
        path=result.path,
        content=result.content,
        truncated=result.truncated,
        binary=result.binary,
        size=result.size,
    )


# ---------- routes ----------


@router.get("/{name}/files", response_model=SkillFileTreeOut)
async def list_skill_files(
    name: str,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
) -> SkillFileTreeOut:
    """Return the skill's master folder as a read-only file tree."""
    name = _validate_skill_name(name)
    # 404 if the skill isn't registered (raises ResourceNotFound → 404).
    await svc.get_skill(name)

    root = file_ops.build_file_tree(pathlib.Path(svc.master_path(name)))
    return SkillFileTreeOut(root=_node_to_out(root))


@router.get("/{name}/files/content", response_model=SkillFileContentOut)
async def read_skill_file(
    name: str,
    path: str = Query(min_length=1),
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
) -> SkillFileContentOut:
    """Read a single file's contents from the skill's master folder."""
    name = _validate_skill_name(name)
    await svc.get_skill(name)  # 404 if the skill isn't registered.

    master = pathlib.Path(svc.master_path(name))
    try:
        result = file_ops.read_skill_file(master, path)
    except ValueError as exc:
        # Path escapes the skill folder — reject before any read happens.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="requested path is outside the skill folder",
        ) from exc
    except (FileNotFoundError, IsADirectoryError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no such file in skill: {path}",
        ) from exc
    return _content_out(result)


@router.put("/{name}/files/content", response_model=SkillFileContentOut)
async def write_skill_file(
    name: str,
    body: SkillFileWriteRequest,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> SkillFileContentOut:
    """Overwrite one existing text file in the skill's master folder."""
    name = _validate_skill_name(name)
    try:
        result = await content_ops.write_skill_file(
            svc, name=name, relpath=body.path, content=body.content, actor=actor
        )
    except ValueError as exc:
        # Path escapes the folder, content too large, or a binary target.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except (FileNotFoundError, IsADirectoryError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no such file in skill: {body.path}",
        ) from exc
    return _content_out(result)
