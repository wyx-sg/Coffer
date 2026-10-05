"""/api/v1/skills/{uid}/files* — skill master-folder viewer, read-only (spec skill-manager
"Show a skill's master folder read-only").

Split out of ``skill_routes.py`` (component size cap): the file-tree and single-file
read endpoints plus their wire schemas. A skill's files are changed on disk, in the
person's own editor; no route writes one.

The skill is addressed by ``{uid}``; the ``path`` query parameter is still a
relative path inside the master folder and is still checked by ``file_ops``,
which is where the traversal guard belongs — it is the layer that touches disk.
"""

from __future__ import annotations

import pathlib
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from coffer.application.skill import file_ops
from coffer.application.skill.service import SkillService
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.skill_dependencies import get_skill_service

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
    type: Literal["file", "dir"]
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


# ---------- helpers ----------


def _abs_paths(root: pathlib.Path, relpath: str) -> tuple[str, str]:
    """Resolve an entry's absolute path and its containing-folder path.

    ``relpath`` is POSIX-relative to the master folder ``root`` (``""`` for the
    root node itself). Returns ``(abs_path, folder_abs_path)`` as strings, which
    back the viewer's open-in-external-editor / reveal-in-file-manager actions.
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


@router.get("/{uid}/files", response_model=SkillFileTreeOut)
async def list_skill_files(
    uid: str,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
) -> SkillFileTreeOut:
    """Return the skill's master folder as a read-only file tree."""
    # 404 if the skill isn't registered (raises ResourceNotFound → 404).
    skill = await svc.get_skill(uid)

    # ``master_path`` takes the NAME, not the uid: the master store's folder on
    # disk is ``~/.coffer/vault/skills/<name>/``, and a skill's name is fixed once
    # registered. So the uid finds the row and the row's name says where its
    # bytes are.
    master = pathlib.Path(svc.master_path(skill.name)).resolve()
    root = file_ops.build_file_tree(master)
    return SkillFileTreeOut(root=_node_to_out(root, master))


@router.get("/{uid}/files/content", response_model=SkillFileContentOut)
async def read_skill_file(
    uid: str,
    path: str = Query(min_length=1),
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
) -> SkillFileContentOut:
    """Read a single file's contents from the skill's master folder."""
    skill = await svc.get_skill(uid)  # 404 if the skill isn't registered.

    master = pathlib.Path(svc.master_path(skill.name)).resolve()
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
