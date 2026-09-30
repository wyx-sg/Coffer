"""POST /{uid}/test — transient upstream health-check route for MCP servers.

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

from coffer.application.resource_service import ResourceService
from coffer.domain.mcp.http_api import HttpApiTransport
from coffer.domain.mcp.secret_target import mcp_destination
from coffer.domain.mcp.server_config import HttpTransport, MCPServerConfig, StdioTransport
from coffer.infrastructure.mcp.http_api_client import HttpApiUpstreamConnection
from coffer.infrastructure.mcp.http_client import HttpUpstreamConnection
from coffer.infrastructure.mcp.persistence import MCPServerHealthRepo
from coffer.infrastructure.mcp.subprocess import StdioUpstreamConnection
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_resource_service
from coffer.surfaces.http.mcp.dependencies import get_health_repo, require_mcp_server
from coffer.surfaces.http.schemas import McpTestResultOut
from coffer.surfaces.http.secret_composition import boundary_resolver, get_secret_store

router = APIRouter(
    prefix="/api/v1/resources/mcp_server",
    tags=["mcp"],
    dependencies=[Depends(require_token)],
)


@router.post("/{uid}/test", response_model=McpTestResultOut)
async def test_mcp_server(
    uid: str,
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
    health_repo: MCPServerHealthRepo = Depends(get_health_repo),  # noqa: B008
    secret_store: Any = Depends(get_secret_store),  # noqa: B008
) -> McpTestResultOut:
    """Open a transient upstream session, run MCP initialize, return health info.
    Persists the result to mcp_server_health so GET /status reflects it."""
    resource = await require_mcp_server(uid, resource_service)

    # Scope (ADR per-agent-resource-scope) is per-AGENT and is enforced at the
    # gateway, which knows
    # the calling session's identity. This is a management route with no such
    # identity, so it does not gate on scope: the owner testing a server they
    # registered may reach it whatever agents it is scoped to.

    config = MCPServerConfig.model_validate(resource.config)

    resolver = boundary_resolver(secret_store)
    destination = mcp_destination(resource.uid, resource.name, config)

    start = time.monotonic()
    try:
        if isinstance(config.transport, StdioTransport):
            # Offload the blocking secret-store read off the event loop.
            overlay = await asyncio.to_thread(
                resolver.materialize, config.transport.secret_refs, destination
            )
            conn: StdioUpstreamConnection | HttpUpstreamConnection | HttpApiUpstreamConnection = (
                StdioUpstreamConnection(
                    transport=config.transport,
                    env_overlay=overlay,
                    spawn_timeout_seconds=config.spawn_timeout_seconds,
                    request_timeout_seconds=config.request_timeout_seconds,
                    # The label, not the identity: this is what the connection puts
                    # in its spawn diagnostics, and a uid there would tell whoever
                    # reads them nothing.
                    server_name=resource.name,
                )
            )
        elif isinstance(config.transport, HttpTransport):
            overlay = await asyncio.to_thread(
                resolver.materialize, config.transport.secret_refs, destination
            )
            conn = HttpUpstreamConnection(
                transport=config.transport,
                header_overlay=overlay,
                spawn_timeout_seconds=config.spawn_timeout_seconds,
                request_timeout_seconds=config.request_timeout_seconds,
            )
        elif isinstance(config.transport, HttpApiTransport):
            # A custom-tool group: its "connection" is served in-process, so the
            # test proves the config loads and the secret is released for it.
            overlay = await asyncio.to_thread(
                resolver.materialize, config.transport.secret_refs, destination
            )
            conn = HttpApiUpstreamConnection(
                transport=config.transport, header_overlay=overlay, server_name=resource.name
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
            # Keyed on the identity, so the result survives a later rename.
            await health_repo.upsert(resource.uid, "healthy", datetime.now(tz=UTC))
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
        await health_repo.upsert(resource.uid, "failing", datetime.now(tz=UTC))
        return McpTestResultOut(
            ok=False,
            latency_ms=latency_ms,
            error_message=str(e),
        )
