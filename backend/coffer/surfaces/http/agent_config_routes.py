"""/api/v1/agents/{name}/config-files and /mcp-install routes (spec 004 v2).

Config-file view + edit (list + read + write) + one-click Coffer-MCP install.
Domain errors (ConfigFileNotAllowed → 404, ConfigFileFormatInvalid → 422,
ShimNotFound → 422, ResourceNotFound → 404) are mapped centrally by
surfaces/http/errors.py.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from coffer.application.agent.config_file_service import (
    AgentConfigFileService,
    ConfigFileContent,
    ConfigFileInfo,
)
from coffer.application.agent.mcp_service import AgentMcpService, McpInstallStatus
from coffer.domain.agent.config_files import ConfigFileFormat
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor as _actor
from coffer.surfaces.http.dependencies import (
    get_agent_config_file_service,
    get_agent_mcp_service,
)

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"],
    dependencies=[Depends(require_token)],
)


class ConfigFileInfoOut(BaseModel):
    key: str
    display_name: str
    path: str
    format: ConfigFileFormat
    exists: bool
    size: int | None
    modified_at: datetime | None


class ConfigFileListOut(BaseModel):
    items: list[ConfigFileInfoOut]


class ConfigFileContentOut(BaseModel):
    key: str
    format: ConfigFileFormat
    exists: bool
    content: str


class ConfigFileWrite(BaseModel):
    content: str


class McpInstallStatusOut(BaseModel):
    installed: bool
    command: str | None


def _info_out(i: ConfigFileInfo) -> ConfigFileInfoOut:
    return ConfigFileInfoOut(
        key=i.key,
        display_name=i.display_name,
        path=i.path,
        format=i.format,
        exists=i.exists,
        size=i.size,
        modified_at=i.modified_at,
    )


def _content_out(c: ConfigFileContent) -> ConfigFileContentOut:
    return ConfigFileContentOut(key=c.key, format=c.format, exists=c.exists, content=c.content)


def _status_out(s: McpInstallStatus) -> McpInstallStatusOut:
    return McpInstallStatusOut(installed=s.installed, command=s.command)


@router.get("/{name}/config-files", response_model=ConfigFileListOut)
async def list_config_files(
    name: str,
    svc: AgentConfigFileService = Depends(get_agent_config_file_service),  # noqa: B008
) -> ConfigFileListOut:
    items = await svc.list_files(name)
    return ConfigFileListOut(items=[_info_out(i) for i in items])


@router.get("/{name}/config-files/{key}", response_model=ConfigFileContentOut)
async def read_config_file(
    name: str,
    key: str,
    svc: AgentConfigFileService = Depends(get_agent_config_file_service),  # noqa: B008
) -> ConfigFileContentOut:
    return _content_out(await svc.read_file(name, key))


@router.put("/{name}/config-files/{key}", response_model=ConfigFileInfoOut)
async def write_config_file(
    name: str,
    key: str,
    body: ConfigFileWrite,
    svc: AgentConfigFileService = Depends(get_agent_config_file_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ConfigFileInfoOut:
    return _info_out(await svc.write_file(name, key, body.content, actor=actor))


@router.get("/{name}/mcp-install", response_model=McpInstallStatusOut)
async def mcp_install_status(
    name: str,
    svc: AgentMcpService = Depends(get_agent_mcp_service),  # noqa: B008
) -> McpInstallStatusOut:
    return _status_out(await svc.status(name))


@router.post("/{name}/mcp-install", response_model=McpInstallStatusOut)
async def install_mcp(
    name: str,
    svc: AgentMcpService = Depends(get_agent_mcp_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> McpInstallStatusOut:
    return _status_out(await svc.install(name, actor=actor))


@router.delete("/{name}/mcp-install", response_model=McpInstallStatusOut)
async def uninstall_mcp(
    name: str,
    svc: AgentMcpService = Depends(get_agent_mcp_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> McpInstallStatusOut:
    return _status_out(await svc.uninstall(name, actor=actor))
