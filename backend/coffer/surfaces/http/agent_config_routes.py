"""/api/v1/agents/{uid}/config-files routes (spec agent-registry).

The listing ("List an agent's config files with their locations") and one
file's read-only preview, as written ("Preview an agent's config file
read-only"). Coffer writes none of
these files on the person's behalf. ResourceNotFound and ConfigFileNotAllowed
→ 404 are mapped centrally by surfaces/http/errors.py.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from coffer.application.agent.config_file_service import (
    AgentConfigFileService,
    ConfigFileInfo,
)
from coffer.domain.agent.config_files import ConfigFileFormat, ConfigFileKind
from coffer.surfaces.http.agent_dependencies import (
    get_agent_config_file_service,
)
from coffer.surfaces.http.agent_type_path import resolve_agent_path
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.errors import error_response

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"],
    dependencies=[Depends(require_token), Depends(resolve_agent_path)],
)


class DirChildOut(BaseModel):
    relpath: str
    path: str
    size: int
    modified_at: datetime


class ConfigFileInfoOut(BaseModel):
    key: str
    display_name: str
    path: str
    folder_path: str
    format: ConfigFileFormat
    kind: ConfigFileKind
    exists: bool
    size: int | None
    modified_at: datetime | None
    files: list[DirChildOut] | None = None


class ConfigFileListOut(BaseModel):
    items: list[ConfigFileInfoOut]


class ConfigFileContentOut(BaseModel):
    """One config file's read-only preview. No fingerprint: there is no write."""

    key: str
    #: Absolute path on disk, for Open in editor / Reveal in Finder.
    abs_path: str
    format: ConfigFileFormat
    #: The file's text as written; empty when ``binary``.
    content: str
    size: int
    truncated: bool
    binary: bool


def _info_out(i: ConfigFileInfo) -> ConfigFileInfoOut:
    return ConfigFileInfoOut(
        key=i.key,
        display_name=i.display_name,
        path=i.path,
        folder_path=i.folder_path,
        format=i.format,
        kind=ConfigFileKind(i.kind),
        exists=i.exists,
        size=i.size,
        modified_at=i.modified_at,
        files=(
            None
            if i.files is None
            else [
                DirChildOut(relpath=f.relpath, path=f.path, size=f.size, modified_at=f.modified_at)
                for f in i.files
            ]
        ),
    )


@router.get("/{uid}/config-files", response_model=ConfigFileListOut)
async def list_config_files(
    uid: str,
    svc: AgentConfigFileService = Depends(get_agent_config_file_service),  # noqa: B008
) -> ConfigFileListOut:
    items = await svc.list_files(uid)
    return ConfigFileListOut(items=[_info_out(i) for i in items])


@router.get("/{uid}/config-files/{key}/content", response_model=ConfigFileContentOut)
async def read_config_file_preview(
    uid: str,
    key: str,
    child: str | None = Query(
        default=None,
        min_length=1,
        description="Under a directory entry: a file's relpath as the listing returns it.",
    ),
    svc: AgentConfigFileService = Depends(get_agent_config_file_service),  # noqa: B008
) -> ConfigFileContentOut:
    """One allowlisted config file, as written, for a read-only preview."""
    try:
        p = await svc.read_preview(uid, key, child)
    except FileNotFoundError:
        return error_response(  # type: ignore[return-value]
            "NOT_FOUND", "the config file does not exist yet"
        )
    return ConfigFileContentOut(
        key=p.key,
        abs_path=p.path,
        format=p.format,
        content=p.content,
        size=p.size,
        truncated=p.truncated,
        binary=p.binary,
    )
