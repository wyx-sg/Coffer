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

from fastapi import APIRouter, Depends, Request

from coffer.application.resource_service import ResourceService
from coffer.domain.mcp.http_api import HttpApiTransport
from coffer.domain.mcp.secret_target import mcp_destination
from coffer.domain.mcp.server_config import HttpTransport, MCPServerConfig, StdioTransport
from coffer.infrastructure.mcp.http_api_client import HttpApiUpstreamConnection
from coffer.infrastructure.mcp.persistence import MCPServerHealthRepo
from coffer.infrastructure.mcp.probe import probe_server
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.credential_composition import boundary_resolver, get_credential_store
from coffer.surfaces.http.dependencies import get_resource_service
from coffer.surfaces.http.mcp.config_test_routes import cancel_on_disconnect
from coffer.surfaces.http.mcp.dependencies import get_health_repo, require_mcp_server
from coffer.surfaces.http.mcp.probe_schemas import McpTestResultOut, result_out

router = APIRouter(
    prefix="/api/v1/resources/mcp_server",
    tags=["mcp"],
    dependencies=[Depends(require_token)],
)


@router.post("/{uid}/test", response_model=McpTestResultOut)
async def test_mcp_server(
    uid: str,
    request: Request,
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
    health_repo: MCPServerHealthRepo = Depends(get_health_repo),  # noqa: B008
    credential_store: Any = Depends(get_credential_store),  # noqa: B008
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

    resolver = boundary_resolver(credential_store)
    destination = mcp_destination(resource.uid, resource.name, config)

    if isinstance(config.transport, (StdioTransport, HttpTransport)):
        # The same probe the Add dialog's unsaved-config test runs (spec
        # mcp-gateway "Test a registered server on demand"): initialize, list
        # the tools, keep a redacted stderr tail, stop the process group.
        # Offload the blocking credential-store read off the event loop.
        try:
            overlay = await asyncio.to_thread(
                resolver.materialize, config.transport.credential_refs, destination
            )
        except Exception as e:  # a binding awaiting approval, a missing secret
            await health_repo.upsert(resource.uid, "failing", datetime.now(tz=UTC))
            return McpTestResultOut(
                ok=False,
                latency_ms=0,
                error_code="stored_secret_not_released",
                error_message=str(e),
                unreleased_secret_keys=sorted(config.transport.credential_refs),
            )
        result = await cancel_on_disconnect(
            request,
            probe_server(
                config.transport,
                overlay,
                spawn_timeout_seconds=config.spawn_timeout_seconds,
                request_timeout_seconds=config.request_timeout_seconds,
                secrets=overlay.values(),
                # The label, not the identity: this is what diagnostics carry.
                server_name=resource.name,
                server_uid=resource.uid,
                # A registered server's URL was accepted at registration; the
                # guard is for URLs typed into a form that is not saved.
                url_guard=None,
            ),
        )
        # Keyed on the identity, so the result survives a later rename.
        await health_repo.upsert(
            resource.uid, "healthy" if result.ok else "failing", datetime.now(tz=UTC)
        )
        return result_out(result)

    start = time.monotonic()
    try:
        if isinstance(config.transport, HttpApiTransport):
            # A custom-tool group: its "connection" is served in-process, so the
            # test proves the config loads and the secret is released for it.
            overlay = await asyncio.to_thread(
                resolver.materialize, config.transport.credential_refs, destination
            )
            conn = HttpApiUpstreamConnection(
                transport=config.transport, header_overlay=overlay, server_name=resource.name
            )
        else:
            return McpTestResultOut(
                ok=False,
                latency_ms=0,
                error_code="unsupported_transport",
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
            error_code="initialize_failed",
            error_message=str(e),
        )
