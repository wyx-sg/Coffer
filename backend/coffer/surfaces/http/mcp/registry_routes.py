"""GET /api/v1/mcp-registry/search — browse the official MCP Registry (ADR-029).

Read-only proxy: the daemon makes the outbound query so the frontend talks only
to localhost. Each result carries an editable config draft (transport + args +
declared env vars, secrets flagged) that feeds the existing Add-MCP-server
pipeline. A registry outage surfaces as 502 ``REGISTRY_UNAVAILABLE``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from coffer.application.mcp.registry_service import MCPRegistrySearchService
from coffer.domain.mcp.registry import RegistryDraft, RegistryServer
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.mcp.registry_dependencies import get_mcp_registry_service

router = APIRouter(
    prefix="/api/v1/mcp-registry",
    tags=["mcp"],
    dependencies=[Depends(require_token)],
)


class RegistryEnvVarOut(BaseModel):
    key: str
    is_secret: bool
    required: bool
    description: str | None


class RegistryDraftOut(BaseModel):
    transport_type: str
    command: str
    args: list[str]
    url: str
    env: list[RegistryEnvVarOut]


class RegistryServerOut(BaseModel):
    name: str
    title: str | None
    description: str
    version: str | None
    registry_type: str | None
    transport_type: str
    installable: bool
    homepage: str | None
    draft: RegistryDraftOut | None


class RegistrySearchOut(BaseModel):
    servers: list[RegistryServerOut]


def _draft_out(d: RegistryDraft | None) -> RegistryDraftOut | None:
    if d is None:
        return None
    return RegistryDraftOut(
        transport_type=d.transport_type,
        command=d.command,
        args=list(d.args),
        url=d.url,
        env=[
            RegistryEnvVarOut(
                key=e.key, is_secret=e.is_secret, required=e.required, description=e.description
            )
            for e in d.env
        ],
    )


def _server_out(s: RegistryServer) -> RegistryServerOut:
    return RegistryServerOut(
        name=s.name,
        title=s.title,
        description=s.description,
        version=s.version,
        registry_type=s.registry_type,
        transport_type=s.transport_type,
        installable=s.installable,
        homepage=s.homepage,
        draft=_draft_out(s.draft),
    )


@router.get("/search", response_model=RegistrySearchOut)
async def search_registry(
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=50),
    svc: MCPRegistrySearchService = Depends(get_mcp_registry_service),  # noqa: B008
) -> RegistrySearchOut:
    servers = await svc.search(q, limit)
    return RegistrySearchOut(servers=[_server_out(s) for s in servers])
