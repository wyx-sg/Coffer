"""/api/v1/agents/{uid}/plugins/{plugin_id}/... read-only routes for what a plugin provides.

Spec agent-registry "Read one installed plugin's detail read-only". The plugin
detail page lists a plugin's skills, commands, subagents and MCP servers; these
routes open each one: a skill's folder (tree + file contents, the same shapes as
a managed skill's), a command's or subagent's markdown file, an MCP server's
``.mcp.json`` entry with every credential masked.

The plugin owns these files, so there is no write counterpart. A name is only
ever matched against what the package really holds (never joined into a path),
and a file path under a skill is resolved by ``file_ops.read_skill_file``, which
refuses anything that leaves the skill's folder.
"""

from __future__ import annotations

import pathlib
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from coffer.application.skill import file_ops
from coffer.domain.agent.mcp_entry_redact import redacted_config
from coffer.domain.agent.plugin_bundle import PluginPart
from coffer.surfaces.http.agent_type_path import resolve_agent_path
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.skill_file_routes import (
    SkillFileContentOut,
    SkillFileTreeOut,
    _content_out,
    _node_to_out,
)
from coffer.surfaces.http.workspace_dependencies import get_agent_plugin_service

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"],
    dependencies=[Depends(require_token), Depends(resolve_agent_path)],
)

_BASE = "/{uid}/plugins/{plugin_id}"


class PluginSkillOut(BaseModel):
    name: str
    description: str | None
    path: str  # the skill's folder on disk


class PluginDocumentOut(BaseModel):
    """A plugin's command or subagent: its markdown file, whole."""

    name: str
    description: str | None
    path: str  # the file on disk
    content: str
    truncated: bool


class PluginMcpServerOut(BaseModel):
    name: str
    path: str  # the ``.mcp.json`` the entry sits in
    # The entry exactly as the file holds it, every env/header value and
    # secret-looking value replaced by a mask.
    config: dict[str, Any]


def _folder(part: PluginPart) -> pathlib.Path:
    return (pathlib.Path(part.root) / part.relpath).resolve()


@router.get(f"{_BASE}/skills/{{skill}}", response_model=PluginSkillOut)
async def get_plugin_skill(
    uid: str,
    plugin_id: str,
    skill: str,
    svc: Any = Depends(get_agent_plugin_service),  # noqa: B008
) -> PluginSkillOut:
    part = await svc.get_part(uid, plugin_id, "skills", skill)
    return PluginSkillOut(name=part.name, description=part.description, path=str(_folder(part)))


@router.get(f"{_BASE}/skills/{{skill}}/files", response_model=SkillFileTreeOut)
async def list_plugin_skill_files(
    uid: str,
    plugin_id: str,
    skill: str,
    svc: Any = Depends(get_agent_plugin_service),  # noqa: B008
) -> SkillFileTreeOut:
    folder = _folder(await svc.get_part(uid, plugin_id, "skills", skill))
    return SkillFileTreeOut(root=_node_to_out(file_ops.build_file_tree(folder), folder))


@router.get(f"{_BASE}/skills/{{skill}}/files/content", response_model=SkillFileContentOut)
async def read_plugin_skill_file(
    uid: str,
    plugin_id: str,
    skill: str,
    path: str = Query(min_length=1),
    svc: Any = Depends(get_agent_plugin_service),  # noqa: B008
) -> SkillFileContentOut:
    """One file of a plugin's skill. A path resolving outside the skill's folder
    (``..``, absolute, escaping symlink) is refused with 400 before anything is read."""
    folder = _folder(await svc.get_part(uid, plugin_id, "skills", skill))
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


async def _document(svc: Any, uid: str, plugin_id: str, kind: str, name: str) -> PluginDocumentOut:
    part: PluginPart = await svc.get_part(uid, plugin_id, kind, name)
    root = pathlib.Path(part.root).resolve()
    try:
        read = file_ops.read_skill_file(root, part.relpath)
    except (ValueError, FileNotFoundError, IsADirectoryError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"no such file: {part.relpath}"
        ) from exc
    return PluginDocumentOut(
        name=part.name,
        description=part.description,
        path=str(root / read.path),
        content=read.content,
        truncated=read.truncated,
    )


@router.get(f"{_BASE}/commands/{{name}}", response_model=PluginDocumentOut)
async def get_plugin_command(
    uid: str,
    plugin_id: str,
    name: str,
    svc: Any = Depends(get_agent_plugin_service),  # noqa: B008
) -> PluginDocumentOut:
    return await _document(svc, uid, plugin_id, "commands", name)


@router.get(f"{_BASE}/agents/{{name}}", response_model=PluginDocumentOut)
async def get_plugin_subagent(
    uid: str,
    plugin_id: str,
    name: str,
    svc: Any = Depends(get_agent_plugin_service),  # noqa: B008
) -> PluginDocumentOut:
    return await _document(svc, uid, plugin_id, "agents", name)


@router.get(f"{_BASE}/mcp-servers/{{name}}", response_model=PluginMcpServerOut)
async def get_plugin_mcp_server(
    uid: str,
    plugin_id: str,
    name: str,
    svc: Any = Depends(get_agent_plugin_service),  # noqa: B008
) -> PluginMcpServerOut:
    part: PluginPart = await svc.get_part(uid, plugin_id, "mcp-servers", name)
    return PluginMcpServerOut(
        name=part.name,
        path=str(pathlib.Path(part.root) / part.relpath),
        config=redacted_config(part.config or {}),
    )
