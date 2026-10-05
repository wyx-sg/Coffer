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

from coffer.application.mcp.custom_tool_secrets import env_secret_resolver
from coffer.application.mcp.runner_detect import missing_runner_of
from coffer.application.resource_service import ResourceService
from coffer.domain.mcp.http_api import HttpApiTransport
from coffer.domain.mcp.probe import failure_reason
from coffer.domain.mcp.secret_target import mcp_destination
from coffer.domain.mcp.server_config import HttpTransport, MCPServerConfig, StdioTransport
from coffer.domain.resource import Resource
from coffer.infrastructure.mcp.http_api_client import HttpApiUpstreamConnection
from coffer.infrastructure.mcp.persistence import MCPServerHealthRepo
from coffer.infrastructure.mcp.probe import probe_server
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_resource_service
from coffer.surfaces.http.handoff_schemas import HandoffOut
from coffer.surfaces.http.mcp.config_test_routes import cancel_on_disconnect
from coffer.surfaces.http.mcp.dependencies import get_health_repo, require_mcp_server
from coffer.surfaces.http.mcp.handoff_views import diagnose_prompt, launcher_prompt
from coffer.surfaces.http.mcp.probe_schemas import McpTestResultOut, result_out
from coffer.surfaces.http.secret_composition import boundary_resolver, get_secret_store

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

    if isinstance(config.transport, (StdioTransport, HttpTransport)):
        # The same probe the Add dialog's unsaved-config test runs (spec
        # mcp-gateway "Report what a test of a registered server found"): initialize, list
        # the tools, keep a redacted stderr tail, stop the process group.
        # Offload the blocking secret-store read off the event loop.
        try:
            overlay = await asyncio.to_thread(
                resolver.materialize, config.transport.secret_refs, destination
            )
        except Exception as e:  # a binding awaiting approval, a missing secret
            await health_repo.upsert(resource.uid, "failing", datetime.now(tz=UTC), "other")
            return McpTestResultOut(
                ok=False,
                latency_ms=0,
                error_code="stored_secret_not_released",
                error_message=str(e),
                unreleased_secret_keys=sorted(config.transport.secret_refs),
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
            resource.uid,
            "healthy" if result.ok else "failing",
            datetime.now(tz=UTC),
            None if result.ok else failure_reason(result.error_code),
        )
        if result.ok:
            return result_out(result)
        return result_out(
            result,
            handoff=await _failed_test_handoff(
                resource, result.error_message, list(result.stderr_tail)
            ),
        )

    start = time.monotonic()
    try:
        if isinstance(config.transport, HttpApiTransport):
            # A custom-tool group: its "connection" is served in-process, so the
            # test proves the config loads and each enabled environment's
            # secret is released for that environment.
            resolve = env_secret_resolver(resolver, resource)
            for env in config.transport.environments:
                if env.enabled:
                    await resolve(env)
            conn = HttpApiUpstreamConnection(
                transport=config.transport, header_overlay={}, server_name=resource.name
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
        await health_repo.upsert(resource.uid, "failing", datetime.now(tz=UTC), "other")
        return McpTestResultOut(
            ok=False,
            latency_ms=latency_ms,
            error_code="initialize_failed",
            error_message=str(e),
            handoff=await _failed_test_handoff(resource, str(e), []),
        )


async def _failed_test_handoff(
    resource: Resource, error: str | None, stderr: list[str]
) -> HandoffOut:
    """The chore a failed test hands to an agent (spec mcp-gateway "Hand a
    failing MCP server's diagnosis to an agent"): installing the launcher when
    it is not found here, else finding the cause from the error and stderr."""
    runner = await asyncio.to_thread(missing_runner_of, resource.config)
    if runner is not None:
        prompt = await asyncio.to_thread(launcher_prompt, resource, runner)
    else:
        prompt = await asyncio.to_thread(diagnose_prompt, resource, error=error, stderr=stderr)
    return HandoffOut(prompt=prompt)
