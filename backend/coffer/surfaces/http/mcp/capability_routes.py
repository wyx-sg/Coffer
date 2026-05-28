"""MCP-specific capability list/enable/disable/refresh/test routes."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status

from coffer.application.audit_service import AuditService
from coffer.application.mcp.credential_resolver import CredentialResolver
from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import UpstreamTimeout, UpstreamUnavailable
from coffer.domain.mcp.server_config import HttpTransport, MCPServerConfig, StdioTransport
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter
from coffer.infrastructure.mcp.http_client import HttpUpstreamConnection
from coffer.infrastructure.mcp.persistence import (
    MCPCapabilityPreferenceRepo,
    MCPInvocationRepo,
    MCPServerHealthRepo,
)
from coffer.infrastructure.mcp.subprocess import StdioUpstreamConnection
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import (
    get_actor,
    get_audit_service,
    get_capability_discovery,
    get_health_repo,
    get_invocation_repo,
    get_preferences_repo,
    get_resource_service,
)
from coffer.surfaces.http.schemas import (
    CapabilityKeyBody,
    CapabilityListOut,
    MCPPromptView,
    MCPResourceView,
    McpServerStatusOut,
    McpTestResultOut,
    MCPToolView,
    _MCPPromptArgument,
)

router = APIRouter(
    prefix="/api/v1/resources/mcp_server",
    tags=["mcp"],
    dependencies=[Depends(require_token)],
)


CapabilityType = Literal["tool", "resource", "prompt"]


@router.get("/{name}/capabilities", response_model=CapabilityListOut)
async def list_capabilities(
    name: str,
    discovery: CapabilityDiscovery = Depends(get_capability_discovery),  # noqa: B008
) -> CapabilityListOut:
    """Return the live (cache-aware) capability list for one MCP server."""
    try:
        tools = await discovery.list_tools(name)
        resources = await discovery.list_resources(name)
        prompts = await discovery.list_prompts(name)
    except UpstreamUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return CapabilityListOut(
        server_name=name,
        tools=[
            MCPToolView(
                prefixed_name=t.prefixed_name,
                original_name=t.original_name,
                description=t.description,
                input_schema=t.input_schema,
                enabled=t.enabled,
            )
            for t in tools
        ],
        resources=[
            MCPResourceView(
                prefixed_uri=r.prefixed_uri,
                original_uri=r.original_uri,
                name=r.name,
                description=r.description,
                mime_type=r.mime_type,
                enabled=r.enabled,
            )
            for r in resources
        ],
        prompts=[
            MCPPromptView(
                prefixed_name=p.prefixed_name,
                original_name=p.original_name,
                description=p.description,
                arguments=[
                    _MCPPromptArgument(
                        name=a.get("name", ""),
                        description=a.get("description"),
                        required=bool(a.get("required", False)),
                    )
                    for a in p.arguments
                ],
                enabled=p.enabled,
            )
            for p in prompts
        ],
        fetched_at=datetime.now(tz=UTC),
        from_cache=False,
    )


@router.get("/{name}/status", response_model=McpServerStatusOut)
async def get_server_status(
    name: str,
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
    prefs: MCPCapabilityPreferenceRepo = Depends(get_preferences_repo),  # noqa: B008
    invocations: MCPInvocationRepo = Depends(get_invocation_repo),  # noqa: B008
    health_repo: MCPServerHealthRepo = Depends(get_health_repo),  # noqa: B008
) -> McpServerStatusOut:
    """Per-server status from persisted state — health record (from /test),
    discovered capabilities, or last invocation. Cheap (DB only); never spawns."""
    # T7: prefer the persisted health state written by POST /test
    health = await health_repo.get(name)
    if health is not None:
        health_status, _ = health
        return McpServerStatusOut(status=health_status)

    resource = await resource_service.get(ResourceRef("mcp_server", name))
    caps = await prefs.list_for(resource.id)
    recent = await invocations.query(resource_name=name, limit=1)
    last = recent[0] if recent else None
    state: Literal["healthy", "failing", "unknown"]
    if last is not None and last.status != "ok":
        state = "failing"
    elif caps or (last is not None and last.status == "ok"):
        state = "healthy"
    else:
        state = "unknown"
    return McpServerStatusOut(status=state)


async def _toggle_capability(
    *,
    name: str,
    capability_type: CapabilityType,
    capability_key: str,
    enabled: bool,
    actor: str,
    resource_service: ResourceService,
    prefs: MCPCapabilityPreferenceRepo,
    audit: AuditService,
) -> Response:
    resource = await resource_service.get(ResourceRef("mcp_server", name))
    updated = await prefs.set_enabled(resource.id, capability_type, capability_key, enabled)
    if updated is None:
        raise HTTPException(
            status_code=404,
            detail=f"capability not found: {capability_type}:{capability_key}",
        )
    await audit.record(
        (
            AuditEventType.CAPABILITY_ENABLED.value
            if enabled
            else AuditEventType.CAPABILITY_DISABLED.value
        ),
        ref=resource.ref,
        actor=actor,
        details={"capability_type": capability_type, "capability_key": capability_key},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Canonical (body-based) form — supports capability_keys containing '/' such as
# resource URIs (e.g., file:///path/to/x). See CODE-001 in PR #14 review.
@router.post(
    "/{name}/capabilities/{capability_type}/enable",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def enable_capability(
    name: str,
    capability_type: CapabilityType,
    body: CapabilityKeyBody = Body(...),  # noqa: B008
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
    prefs: MCPCapabilityPreferenceRepo = Depends(get_preferences_repo),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> Response:
    """Enable a specific capability for the named MCP server."""
    return await _toggle_capability(
        name=name,
        capability_type=capability_type,
        capability_key=body.capability_key,
        enabled=True,
        actor=actor,
        resource_service=resource_service,
        prefs=prefs,
        audit=audit,
    )


@router.post(
    "/{name}/capabilities/{capability_type}/disable",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def disable_capability(
    name: str,
    capability_type: CapabilityType,
    body: CapabilityKeyBody = Body(...),  # noqa: B008
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
    prefs: MCPCapabilityPreferenceRepo = Depends(get_preferences_repo),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> Response:
    """Disable a specific capability for the named MCP server."""
    return await _toggle_capability(
        name=name,
        capability_type=capability_type,
        capability_key=body.capability_key,
        enabled=False,
        actor=actor,
        resource_service=resource_service,
        prefs=prefs,
        audit=audit,
    )


# Legacy (path-based) form — kept for backward compatibility with clients that
# already shipped against the old URL. Only safe for capability_keys WITHOUT '/'.
# New code should use the body-based routes above.
@router.post(
    "/{name}/capabilities/{capability_type}/{capability_key}/enable",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    include_in_schema=False,
)
async def enable_capability_legacy(
    name: str,
    capability_type: CapabilityType,
    capability_key: str,
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
    prefs: MCPCapabilityPreferenceRepo = Depends(get_preferences_repo),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> Response:
    return await _toggle_capability(
        name=name,
        capability_type=capability_type,
        capability_key=capability_key,
        enabled=True,
        actor=actor,
        resource_service=resource_service,
        prefs=prefs,
        audit=audit,
    )


@router.post(
    "/{name}/capabilities/{capability_type}/{capability_key}/disable",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    include_in_schema=False,
)
async def disable_capability_legacy(
    name: str,
    capability_type: CapabilityType,
    capability_key: str,
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
    prefs: MCPCapabilityPreferenceRepo = Depends(get_preferences_repo),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> Response:
    return await _toggle_capability(
        name=name,
        capability_type=capability_type,
        capability_key=capability_key,
        enabled=False,
        actor=actor,
        resource_service=resource_service,
        prefs=prefs,
        audit=audit,
    )


@router.post("/{name}/refresh", response_model=CapabilityListOut)
async def refresh_capabilities(
    name: str,
    discovery: CapabilityDiscovery = Depends(get_capability_discovery),  # noqa: B008
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> CapabilityListOut:
    """Invalidate the discovery cache for this server and re-query upstream.

    Returns 404 if the named server is not registered.
    """
    # Raises ResourceNotFound (→ 404) if this server doesn't exist.
    await resource_service.get(ResourceRef("mcp_server", name))
    discovery.invalidate(name)
    return await list_capabilities(name, discovery)


@router.post("/{name}/test", response_model=McpTestResultOut)
async def test_mcp_server(
    name: str,
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
    health_repo: MCPServerHealthRepo = Depends(get_health_repo),  # noqa: B008
) -> McpTestResultOut:
    """Open a transient upstream session, run MCP initialize, return health info.
    Persists the result to mcp_server_health so GET /status reflects it."""
    resource = await resource_service.get(ResourceRef("mcp_server", name))
    config = MCPServerConfig.model_validate(resource.config)

    keyring_adapter = KeyringAdapter()
    resolver = CredentialResolver(keyring_adapter)

    start = time.monotonic()
    try:
        if isinstance(config.transport, StdioTransport):
            overlay = resolver.materialize(config.transport.credential_refs)
            conn: StdioUpstreamConnection | HttpUpstreamConnection = StdioUpstreamConnection(
                transport=config.transport,
                env_overlay=overlay,
                spawn_timeout_seconds=config.spawn_timeout_seconds,
                request_timeout_seconds=config.request_timeout_seconds,
                server_name=name,
            )
        elif isinstance(config.transport, HttpTransport):
            overlay = resolver.materialize(config.transport.credential_refs)
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
    except (UpstreamUnavailable, UpstreamTimeout) as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        await health_repo.upsert(name, "failing", datetime.now(tz=UTC))
        return McpTestResultOut(
            ok=False,
            latency_ms=latency_ms,
            error_message=str(e),
        )
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        await health_repo.upsert(name, "failing", datetime.now(tz=UTC))
        return McpTestResultOut(
            ok=False,
            latency_ms=latency_ms,
            error_message=str(e),
        )
