"""/api/v1/agents/{uid}/config-files route (spec agent-registry).

The listing is the only config-file route: Coffer serves no config file's
content and writes none on the person's behalf ("List an agent's config files
with their locations"). ResourceNotFound → 404 is mapped centrally by
surfaces/http/errors.py.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
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
