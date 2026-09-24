"""MCP-specific capability list/enable/disable/refresh routes.

Every route here addresses its server by the resource's immutable ``uid``
(ADR resource-identity-is-an-immutable-uid) and resolves it to the row once,
through ``require_mcp_server``. The NAME the row carries is then what goes to
capability discovery, which is keyed on it because the wire namespace
``<server>__<tool>`` is built from the label.

The transient upstream health-check route (POST /{uid}/test) lives in
``server_test_routes`` to keep this module under the file-size limit.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status

from coffer.application.audit_service import AuditService
from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.mcp.invocation_outcome import is_upstream_answered
from coffer.application.mcp.runner_detect import missing_runner
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import UpstreamTimeout, UpstreamUnavailable
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Resource
from coffer.infrastructure.mcp.persistence import (
    MCPCapabilityPreferenceRepo,
    MCPInvocationRepo,
    MCPServerHealthRepo,
)
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import (
    get_actor,
    get_audit_service,
    get_resource_service,
)
from coffer.surfaces.http.mcp.capability_views import (
    cached_capability_list,
    live_capability_list,
)
from coffer.surfaces.http.mcp.dependencies import (
    get_capability_discovery,
    get_health_repo,
    get_invocation_repo,
    get_preferences_repo,
    require_mcp_server,
)
from coffer.surfaces.http.schemas import (
    CapabilityKeyBody,
    CapabilityListOut,
    McpServerStatusOut,
)

router = APIRouter(
    prefix="/api/v1/resources/mcp_server",
    tags=["mcp"],
    dependencies=[Depends(require_token)],
)


CapabilityType = Literal["tool", "resource", "prompt"]

# Hard ceiling on the management capabilities page so a wedged
# upstream can't hang it for the supervisor's full retry ladder (~minutes).
# Deliberately LARGER than the gateway's 5 s PER_SERVER_LIST_TIMEOUT: this
# page may trigger a cold spawn, and spawn_timeout defaults to 30 s — a 5 s
# budget would cancel every healthy-but-slow first spawn mid-initialize.
_CAPABILITY_LIST_TIMEOUT = 35.0

# How many recent invocation rows the status route looks through for one that
# reached the server (``denied`` rows are skipped). Bounded so a burst of
# refused calls costs one small query, not a scan of the log.
_STATUS_LOOKBACK = 20


async def _capability_list(
    resource: Resource,
    discovery: CapabilityDiscovery,
    prefs: MCPCapabilityPreferenceRepo,
) -> CapabilityListOut:
    """The live (cache-aware) capability list for one already-resolved server.

    Shared by GET /{uid}/capabilities and POST /{uid}/refresh so the refresh
    route does not have to re-enter the handler function (and re-resolve, or
    worse, inherit the handler's ``Depends`` defaults as if they were real
    collaborators).

    This is the management view: it returns every discovered capability with
    its ``enabled`` flag (including disabled ones) so the UI can show and
    re-enable them. The three discovery calls run concurrently under a single
    timeout budget.

    When the upstream can't be live-queried — a *disabled* server (the gateway
    won't connect it) or an unreachable one — fall back to the persisted
    enable/disable preferences so the detail page still lists the
    previously-discovered capabilities (name + enabled flag) with
    ``from_cache=True``, instead of a dead-end "couldn't load" error. Only when
    nothing was ever discovered (no persisted rows) does the upstream failure
    surface as ``UpstreamUnavailable`` (→ UPSTREAM_UNAVAILABLE).
    """
    name = resource.name
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
        cached = await cached_capability_list(resource, prefs)
        if cached is not None:
            return cached
        if isinstance(e, TimeoutError):
            raise UpstreamUnavailable(
                f"{name!r} did not respond within {_CAPABILITY_LIST_TIMEOUT:.0f}s"
            ) from e
        raise
    except BaseException:
        # Any other failure: reap siblings and let the global handler map it.
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    return live_capability_list(name, tools, resources, prompts)


@router.get("/{uid}/capabilities", response_model=CapabilityListOut)
async def list_capabilities(
    uid: str,
    discovery: CapabilityDiscovery = Depends(get_capability_discovery),  # noqa: B008
    prefs: MCPCapabilityPreferenceRepo = Depends(get_preferences_repo),  # noqa: B008
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> CapabilityListOut:
    """Return the live (cache-aware) capability list for one MCP server.

    404s (via ``require_mcp_server``) before any upstream work when the uid
    names nothing, which is why the response's ``server_name`` is the resolved
    label rather than the path segment echoed back: a capabilities page headed
    by an opaque uid would be unreadable.
    """
    resource = await require_mcp_server(uid, resource_service)
    return await _capability_list(resource, discovery, prefs)


@router.get("/{uid}/status", response_model=McpServerStatusOut)
async def get_server_status(
    uid: str,
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
    prefs: MCPCapabilityPreferenceRepo = Depends(get_preferences_repo),  # noqa: B008
    invocations: MCPInvocationRepo = Depends(get_invocation_repo),  # noqa: B008
    health_repo: MCPServerHealthRepo = Depends(get_health_repo),  # noqa: B008
) -> McpServerStatusOut:
    """Per-server status from persisted state — health record (from /test),
    discovered capabilities, or last invocation. Cheap (DB only + one PATH
    lookup); never spawns."""
    resource = await require_mcp_server(uid, resource_service)
    # A stdio launcher that does not resolve on THIS machine (synced server,
    # runner not installed here) — surfaced so the cause is visible.
    runner = await asyncio.to_thread(_missing_runner_of, resource)

    # T7: prefer the persisted health state written by POST /test. Both the
    # health record and the invocation log are keyed on the uid, so a renamed
    # server keeps the status it earned instead of reading "unknown" until the
    # next test.
    health = await health_repo.get(resource.uid)
    if health is not None:
        health_status, _ = health
        return McpServerStatusOut(status=health_status, missing_runner=runner)

    caps = await prefs.list_for(resource.id)
    # Health is read from the most recent call that says something about the
    # SERVER. A ``denied`` row never reached it (a disabled capability, an
    # out-of-scope session), so it is skipped. An ``error`` the upstream
    # answered — an ``isError`` tool result, a well-formed JSON-RPC error — is
    # the tool failing over a healthy connection, which is evidence the server
    # is up (spec mcp-gateway "Route calls to the originating upstream" ties
    # unhealthy to a transport failure or a crash, not to a tool's answer).
    recent = await invocations.query(resource_uid=resource.uid, limit=_STATUS_LOOKBACK)
    last = next((inv for inv in recent if inv.status != "denied"), None)
    state: Literal["healthy", "failing", "unknown"]
    if last is not None and last.status != "ok" and not is_upstream_answered(last):
        state = "failing"
    elif caps or last is not None:
        state = "healthy"
    else:
        state = "unknown"
    return McpServerStatusOut(status=state, missing_runner=runner)


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
    uid: str,
    capability_type: CapabilityType,
    capability_key: str,
    enabled: bool,
    actor: str,
    resource_service: ResourceService,
    prefs: MCPCapabilityPreferenceRepo,
    audit: AuditService,
) -> Response:
    resource = await require_mcp_server(uid, resource_service)
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
        resource=resource,
        actor=actor,
        details={"capability_type": capability_type, "capability_key": capability_key},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Canonical (body-based) form — supports capability_keys containing '/' such as
# resource URIs (e.g., file:///path/to/x).
@router.post(
    "/{uid}/capabilities/{capability_type}/enable",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def enable_capability(
    uid: str,
    capability_type: CapabilityType,
    body: CapabilityKeyBody = Body(...),  # noqa: B008
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
    prefs: MCPCapabilityPreferenceRepo = Depends(get_preferences_repo),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> Response:
    """Enable a specific capability for the MCP server this uid names."""
    return await _toggle_capability(
        uid=uid,
        capability_type=capability_type,
        capability_key=body.capability_key,
        enabled=True,
        actor=actor,
        resource_service=resource_service,
        prefs=prefs,
        audit=audit,
    )


@router.post(
    "/{uid}/capabilities/{capability_type}/disable",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def disable_capability(
    uid: str,
    capability_type: CapabilityType,
    body: CapabilityKeyBody = Body(...),  # noqa: B008
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
    prefs: MCPCapabilityPreferenceRepo = Depends(get_preferences_repo),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> Response:
    """Disable a specific capability for the MCP server this uid names."""
    return await _toggle_capability(
        uid=uid,
        capability_type=capability_type,
        capability_key=body.capability_key,
        enabled=False,
        actor=actor,
        resource_service=resource_service,
        prefs=prefs,
        audit=audit,
    )


@router.post("/{uid}/refresh", response_model=CapabilityListOut)
async def refresh_capabilities(
    uid: str,
    discovery: CapabilityDiscovery = Depends(get_capability_discovery),  # noqa: B008
    prefs: MCPCapabilityPreferenceRepo = Depends(get_preferences_repo),  # noqa: B008
    resource_service: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> CapabilityListOut:
    """Invalidate the discovery cache for this server and re-query upstream.

    Returns 404 if the uid names no MCP server.
    """
    resource = await require_mcp_server(uid, resource_service)
    # The discovery cache is keyed on the name, the same key its upstream
    # sessions are, so invalidating it means invalidating under the label the
    # row carries right now.
    discovery.invalidate(resource.name)
    return await _capability_list(resource, discovery, prefs)
