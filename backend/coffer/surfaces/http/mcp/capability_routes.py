"""MCP-specific capability list/enable/disable/refresh/test routes."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status

from coffer.application.audit_service import AuditService
from coffer.application.credentials.resolver import CredentialResolver
from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.mcp.runner_install import (
    missing_runner,
    runner_installable,
)
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import UpstreamTimeout, UpstreamUnavailable
from coffer.domain.mcp.server_config import HttpTransport, MCPServerConfig, StdioTransport
from coffer.domain.resource import Resource, ResourceRef
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
    get_credential_store,
    get_health_repo,
    get_invocation_repo,
    get_preferences_repo,
    get_resource_service,
)
from coffer.surfaces.http.mcp.capability_views import (
    cached_capability_list,
    live_capability_list,
)
from coffer.surfaces.http.schemas import (
    CapabilityKeyBody,
    CapabilityListOut,
    McpServerStatusOut,
    McpTestResultOut,
)

router = APIRouter(
    prefix="/api/v1/resources/mcp_server",
    tags=["mcp"],
    dependencies=[Depends(require_token)],
)


CapabilityType = Literal["tool", "resource", "prompt"]

# CODE-M2: hard ceiling on the management capabilities page so a wedged
# upstream can't hang it for the supervisor's full retry ladder (~minutes).
# Deliberately LARGER than the gateway's 5 s PER_SERVER_LIST_TIMEOUT: this
# page may trigger a cold spawn, and spawn_timeout defaults to 30 s — a 5 s
# budget would cancel every healthy-but-slow first spawn mid-initialize.
_CAPABILITY_LIST_TIMEOUT = 35.0


@router.get("/{name}/capabilities", response_model=CapabilityListOut)
async def list_capabilities(
    name: str,
    discovery: CapabilityDiscovery = Depends(get_capability_discovery),  # noqa: B008
    prefs: MCPCapabilityPreferenceRepo = Depends(get_preferences_repo),  # noqa: B008
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> CapabilityListOut:
    """Return the live (cache-aware) capability list for one MCP server.

    This is the management surface: it returns every discovered capability
    with its ``enabled`` flag (including disabled ones) so the UI can show and
    re-enable them. The three discovery calls run concurrently under a single
    timeout budget (CODE-M2).

    When the upstream can't be live-queried — a *disabled* server (the gateway
    won't connect it) or an unreachable one — fall back to the persisted
    enable/disable preferences so the detail page still lists the
    previously-discovered capabilities (name + enabled flag) with
    ``from_cache=True``, instead of a dead-end "couldn't load" error. Only when
    nothing was ever discovered (no persisted rows) does the upstream failure
    surface as ``UpstreamUnavailable`` (→ UPSTREAM_UNAVAILABLE).
    """
    tasks: list[asyncio.Task[Any]] = [
        asyncio.ensure_future(discovery.list_tools(name, include_disabled=True)),
        asyncio.ensure_future(discovery.list_resources(name, include_disabled=True)),
        asyncio.ensure_future(discovery.list_prompts(name, include_disabled=True)),
    ]
    try:
        tools, resources, prompts = await asyncio.wait_for(
            asyncio.gather(*tasks),
            timeout=_CAPABILITY_LIST_TIMEOUT,
        )
    except (TimeoutError, UpstreamUnavailable, UpstreamTimeout) as e:
        # A disabled/unreachable/hung upstream. gather() propagates the first
        # child failure WITHOUT cancelling the siblings (wait_for's timeout path
        # does) — reap them so they don't grind the spawn retry ladder in the
        # background, then serve the persisted preferences as a degraded view.
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        cached = await cached_capability_list(name, prefs, resource_service)
        if cached is not None:
            return cached
        if isinstance(e, TimeoutError):
            raise UpstreamUnavailable(
                f"{name!r} did not respond within {_CAPABILITY_LIST_TIMEOUT:.0f}s"
            ) from e
        raise
    except BaseException:
        # Any other failure (e.g. ResourceNotFound for an unknown server → 404):
        # reap siblings and let the global handler map it.
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    return live_capability_list(name, tools, resources, prompts)


@router.get("/{name}/status", response_model=McpServerStatusOut)
async def get_server_status(
    name: str,
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
    prefs: MCPCapabilityPreferenceRepo = Depends(get_preferences_repo),  # noqa: B008
    invocations: MCPInvocationRepo = Depends(get_invocation_repo),  # noqa: B008
    health_repo: MCPServerHealthRepo = Depends(get_health_repo),  # noqa: B008
) -> McpServerStatusOut:
    """Per-server status from persisted state — health record (from /test),
    discovered capabilities, or last invocation. Cheap (DB only + one PATH
    lookup); never spawns."""
    resource = await resource_service.get(ResourceRef("mcp_server", name))
    # A stdio launcher that does not resolve on THIS machine (synced server,
    # runner not installed here) — surfaced with a one-click install.
    runner = await asyncio.to_thread(_missing_runner_of, resource)
    installable = runner is not None and runner_installable(runner)

    # T7: prefer the persisted health state written by POST /test
    health = await health_repo.get(name)
    if health is not None:
        health_status, _ = health
        return McpServerStatusOut(
            status=health_status, missing_runner=runner, runner_installable=installable
        )

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
    return McpServerStatusOut(status=state, missing_runner=runner, runner_installable=installable)


def _missing_runner_of(resource: Resource) -> str | None:
    try:
        config = MCPServerConfig.model_validate(resource.config)
    except Exception:
        return None
    if config.transport.type != "stdio":
        return None
    return missing_runner(config.transport.command)


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
    credential_store: Any = Depends(get_credential_store),  # noqa: B008
) -> McpTestResultOut:
    """Open a transient upstream session, run MCP initialize, return health info.
    Persists the result to mcp_server_health so GET /status reflects it."""
    resource = await resource_service.get(ResourceRef("mcp_server", name))
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
