"""POST /{name}/test — transient upstream health-check route for MCP servers.

Extracted from capability_routes.py to keep that module under the file-size
limit. Named `server_test_routes` (not `test_routes`) so its filename never
tempts a broadened pytest collection scope into treating this application
module as a test module — pytest here is scoped to `testpaths = ["tests"]`
(backend/pyproject.toml), but the name stays unambiguous regardless.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends

from coffer.application.credentials.resolver import CredentialResolver
from coffer.application.resource_service import ResourceService
from coffer.domain.mcp.server_config import HttpTransport, MCPServerConfig, StdioTransport
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.mcp.http_client import HttpUpstreamConnection
from coffer.infrastructure.mcp.persistence import MCPServerHealthRepo
from coffer.infrastructure.mcp.subprocess import StdioUpstreamConnection
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import (
    get_credential_store,
    get_health_repo,
    get_resource_service,
)
from coffer.surfaces.http.schemas import McpTestResultOut

router = APIRouter(
    prefix="/api/v1/resources/mcp_server",
    tags=["mcp"],
    dependencies=[Depends(require_token)],
)


@router.post("/{name}/test", response_model=McpTestResultOut)
async def test_mcp_server(
    name: str,
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
    health_repo: MCPServerHealthRepo = Depends(get_health_repo),  # noqa: B008
    credential_store: Any = Depends(get_credential_store),  # noqa: B008
) -> McpTestResultOut:
    """Open a transient upstream session, run MCP initialize, return health info.
    Persists the result to mcp_server_health so GET /status reflects it."""
    resource = await resource_service.get(ResourceRef("mcp_server", name))

    # Scope (ADR per-agent-resource-scope) is per-AGENT and is enforced at the
    # gateway, which knows
    # the calling session's identity. This is a management route with no such
    # identity, so it does not gate on scope: the owner testing a server they
    # registered may reach it whatever agents it is scoped to.

    config = MCPServerConfig.model_validate(resource.config)

    resolver = CredentialResolver(credential_store)

    start = time.monotonic()
    try:
        if isinstance(config.transport, StdioTransport):
            # CODE-034: offload the blocking credential-store read off the event loop.
            overlay = await asyncio.to_thread(
                resolver.materialize, config.transport.credential_refs
            )
            conn: StdioUpstreamConnection | HttpUpstreamConnection = StdioUpstreamConnection(
                transport=config.transport,
                env_overlay=overlay,
                spawn_timeout_seconds=config.spawn_timeout_seconds,
                request_timeout_seconds=config.request_timeout_seconds,
                server_name=name,
            )
        elif isinstance(config.transport, HttpTransport):
            overlay = await asyncio.to_thread(
                resolver.materialize, config.transport.credential_refs
            )
            conn = HttpUpstreamConnection(
                transport=config.transport,
                header_overlay=overlay,
                spawn_timeout_seconds=config.spawn_timeout_seconds,
                request_timeout_seconds=config.request_timeout_seconds,
            )
        else:
            return McpTestResultOut(
                ok=False,
                latency_ms=0,
                error_message=f"unsupported transport: {type(config.transport).__name__}",
            )
        try:
            caps = await conn.spawn_and_initialize()
            latency_ms = int((time.monotonic() - start) * 1000)
            await health_repo.upsert(name, "healthy", datetime.now(tz=UTC))
            return McpTestResultOut(
                ok=True,
                latency_ms=latency_ms,
                protocol_version="2025-06-18",
                server_capabilities=caps,
                error_message=None,
            )
        finally:
            await conn.close()
    except Exception as e:  # incl. UpstreamUnavailable / UpstreamTimeout
        latency_ms = int((time.monotonic() - start) * 1000)
        await health_repo.upsert(name, "failing", datetime.now(tz=UTC))
        return McpTestResultOut(
            ok=False,
            latency_ms=latency_ms,
            error_message=str(e),
        )
