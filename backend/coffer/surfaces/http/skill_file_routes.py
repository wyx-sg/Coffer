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
    abs_path: str  # resolved absolute path of this entry on disk
    folder_abs_path: str  # absolute path of this entry's containing folder
    type: str  # "file" | "dir"
    size: int | None = None
    truncated: bool = False  # directory clipped at the max walk depth
    children: list[SkillFileNodeOut] = Field(default_factory=list)


class SkillFileTreeOut(BaseModel):
    root: SkillFileNodeOut


class SkillFileContentOut(BaseModel):
    path: str  # POSIX, relative to the master folder root
    abs_path: str  # resolved absolute path of the file on disk
    folder_abs_path: str  # absolute path of the file's containing folder
    content: str  # empty when ``binary`` is true
    truncated: bool
    binary: bool
    size: int


class SkillFileWriteRequest(BaseModel):
    path: str = Field(min_length=1)  # POSIX, relative to the master folder root
    content: str  # full new file contents (UTF-8)


# ---------- helpers ----------


def _abs_paths(root: pathlib.Path, relpath: str) -> tuple[str, str]:
    """Resolve an entry's absolute path and its containing-folder path.

    ``relpath`` is POSIX-relative to the master folder ``root`` (``""`` for the
    root node itself). Returns ``(abs_path, folder_abs_path)`` as strings; the
    UI viewer is read-only and uses these for open-in-editor / reveal.
    """
    target = root if relpath == "" else root / relpath
    return str(target), str(target.parent)


def _node_to_out(node: file_ops.FileNode, root: pathlib.Path) -> SkillFileNodeOut:
    abs_path, folder_abs_path = _abs_paths(root, node.path)
    return SkillFileNodeOut(
        name=node.name,
        path=node.path,
        abs_path=abs_path,
        folder_abs_path=folder_abs_path,
        type=node.type,
        size=node.size,
        truncated=node.truncated,
        children=[_node_to_out(c, root) for c in node.children],
    )


def _content_out(result: file_ops.FileContent, root: pathlib.Path) -> SkillFileContentOut:
    abs_path, folder_abs_path = _abs_paths(root, result.path)
    return SkillFileContentOut(
        path=result.path,
        abs_path=abs_path,
        folder_abs_path=folder_abs_path,
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

    master = pathlib.Path(svc.master_path(name)).resolve()
    root = file_ops.build_file_tree(master)
    return SkillFileTreeOut(root=_node_to_out(root, master))


@router.get("/{name}/files/content", response_model=SkillFileContentOut)
async def read_skill_file(
    name: str,
    path: str = Query(min_length=1),
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
) -> SkillFileContentOut:
    """Read a single file's contents from the skill's master folder."""
    name = _validate_skill_name(name)
    await svc.get_skill(name)  # 404 if the skill isn't registered.

    master = pathlib.Path(svc.master_path(name)).resolve()
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
    return _content_out(result, master)


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
    master = pathlib.Path(svc.master_path(name)).resolve()
    return _content_out(result, master)
