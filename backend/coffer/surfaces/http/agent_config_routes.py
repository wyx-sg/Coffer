"""/api/v1/agents/{uid}/config-files routes (spec agent-registry).

Config-file view + edit (list + read + write) and directory-entry child files
(read + write + delete under `/files/{relpath}`). Writes carry an optional
`expected_fingerprint` for optimistic concurrency ("Reject stale config-file
writes by fingerprint"). Domain errors
(ConfigFileNotAllowed → 404, ConfigFileFormatInvalid → 422, ConfigFileStale → 409,
ResourceNotFound → 404) are mapped centrally by surfaces/http/errors.py.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from coffer.application.agent.config_file_service import (
    AgentConfigFileService,
    ConfigFileContent,
    ConfigFileInfo,
)
from coffer.domain.agent.config_files import ConfigFileFormat, ConfigFileKind
from coffer.surfaces.http.agent_dependencies import (
    get_agent_config_file_service,
)
from coffer.surfaces.http.agent_type_path import resolve_agent_path
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor as _actor

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"],
    dependencies=[Depends(require_token), Depends(resolve_agent_path)],
)


class DirChildOut(BaseModel):
    relpath: str
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
    key: str
    path: str
    folder_path: str
    format: ConfigFileFormat
    exists: bool
    content: str
    fingerprint: str


class ConfigFileWrite(BaseModel):
    content: str
    expected_fingerprint: str | None = None


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
                DirChildOut(relpath=f.relpath, size=f.size, modified_at=f.modified_at)
                for f in i.files
            ]
        ),
    )


def _content_out(c: ConfigFileContent) -> ConfigFileContentOut:
    return ConfigFileContentOut(
        key=c.key,
        path=c.path,
        folder_path=c.folder_path,
        format=c.format,
        exists=c.exists,
        content=c.content,
        fingerprint=c.fingerprint,
    )


@router.get("/{uid}/config-files", response_model=ConfigFileListOut)
async def list_config_files(
    uid: str,
    svc: AgentConfigFileService = Depends(get_agent_config_file_service),  # noqa: B008
) -> ConfigFileListOut:
    items = await svc.list_files(uid)
    return ConfigFileListOut(items=[_info_out(i) for i in items])


# Child-file routes are registered BEFORE the bare `{key}` routes so the more
# specific `/files/` path can never be captured by a `{key}` match.
@router.get("/{uid}/config-files/{key}/files/{relpath:path}", response_model=ConfigFileContentOut)
async def read_config_dir_file(
    uid: str,
    key: str,
    relpath: str,
    svc: AgentConfigFileService = Depends(get_agent_config_file_service),  # noqa: B008
) -> ConfigFileContentOut:
    return _content_out(await svc.read_child(uid, key, relpath))


@router.put("/{uid}/config-files/{key}/files/{relpath:path}", response_model=ConfigFileInfoOut)
async def write_config_dir_file(
    uid: str,
    key: str,
    relpath: str,
    body: ConfigFileWrite,
    svc: AgentConfigFileService = Depends(get_agent_config_file_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ConfigFileInfoOut:
    return _info_out(
        await svc.write_child(
            uid,
            key,
            relpath,
            body.content,
            expected_fingerprint=body.expected_fingerprint,
            actor=actor,
        )
    )


@router.delete(
    "/{uid}/config-files/{key}/files/{relpath:path}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_config_dir_file(
    uid: str,
    key: str,
    relpath: str,
    svc: AgentConfigFileService = Depends(get_agent_config_file_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> None:
    await svc.delete_child(uid, key, relpath, actor=actor)


@router.get("/{uid}/config-files/{key}", response_model=ConfigFileContentOut)
async def read_config_file(
    uid: str,
    key: str,
    svc: AgentConfigFileService = Depends(get_agent_config_file_service),  # noqa: B008
) -> ConfigFileContentOut:
    return _content_out(await svc.read_file(uid, key))


@router.put("/{uid}/config-files/{key}", response_model=ConfigFileInfoOut)
async def write_config_file(
    uid: str,
    key: str,
    body: ConfigFileWrite,
    svc: AgentConfigFileService = Depends(get_agent_config_file_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ConfigFileInfoOut:
    return _info_out(
        await svc.write_file(
            uid, key, body.content, expected_fingerprint=body.expected_fingerprint, actor=actor
        )
    )
