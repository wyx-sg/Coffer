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
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends

from coffer.application.credentials.resolver import CredentialResolver
from coffer.application.resource_service import ResourceService
from coffer.domain.mcp.server_config import HttpTransport, MCPServerConfig, StdioTransport
from coffer.domain.resource import ResourceRef
from coffer.domain.scope import machine_in_scope
from coffer.infrastructure.mcp.http_client import HttpUpstreamConnection
from coffer.infrastructure.mcp.persistence import MCPServerHealthRepo
from coffer.infrastructure.mcp.subprocess import StdioUpstreamConnection
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import (
    get_credential_store,
    get_health_repo,
    get_local_machine_id_provider,
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
    local_machine_id: Callable[[], Awaitable[str | None]] = Depends(  # noqa: B008
        get_local_machine_id_provider
    ),
) -> McpTestResultOut:
    """Open a transient upstream session, run MCP initialize, return health info.
    Persists the result to mcp_server_health so GET /status reflects it."""
    resource = await resource_service.get(ResourceRef("mcp_server", name))

    # ADR-045 machine axis (Task 8): this route builds its own transient
    # upstream connection directly (it does NOT go through the process
    # supervisor), so it must repeat the supervisor's scope gate itself —
    # otherwise a server scoped to a different machine would spawn here even
    # though every other path (sessions, refresh/discovery) refuses it.
    # FR-020: an out-of-scope server is never spawned and is indistinguishable
    # from an unregistered one on this machine. No provider wired (local is
    # None) means legacy behavior: no filtering at all.
    local = await local_machine_id()
    if local is not None and not machine_in_scope(resource.scope, local):
        return McpTestResultOut(
            ok=False,
            latency_ms=0,
            error_message=f"{name!r} is not in scope on this machine",
        )

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
