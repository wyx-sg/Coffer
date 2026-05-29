"""Live capability discovery for MCP gateway sessions.

Per ADR-004, the DB stores only user preferences (enabled/disabled per
capability key). The actual tool/resource/prompt list is queried live
from the upstream on each request, with a short in-process cache.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from coffer.application.audit_service import AuditService
from coffer.application.mcp.ports import MCPCapabilityPreferenceRepoPort
from coffer.application.mcp.supervisor import SubprocessSupervisor
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.mcp.capability import (
    CapabilityType,
    MCPPrompt,
    MCPPromptArgument,
    MCPResource,
    MCPTool,
)
from coffer.domain.mcp.namespace import prefix_prompt, prefix_resource_uri, prefix_tool
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import ResourceRef

_DEFAULT_CACHE_TTL_SECONDS = 60.0


@dataclass
class _UpstreamCache:
    """Per-(session, server) in-memory cache."""

    tools: list[MCPTool] | None = None
    resources: list[MCPResource] | None = None
    prompts: list[MCPPrompt] | None = None
    tools_fetched_at: float = 0.0
    resources_fetched_at: float = 0.0
    prompts_fetched_at: float = 0.0
    locks: dict[str, asyncio.Lock] = field(default_factory=dict)


# Maps CapabilityType to (list_attr, timestamp_attr) names on _UpstreamCache
_ATTRS_BY_TYPE: dict[Literal["tool", "resource", "prompt"], tuple[str, str]] = {
    "tool": ("tools", "tools_fetched_at"),
    "resource": ("resources", "resources_fetched_at"),
    "prompt": ("prompts", "prompts_fetched_at"),
}


@dataclass(frozen=True)
class DiscoveredTool:
    """A tool the gateway is about to surface, post-filter, with prefix."""

    prefixed_name: str
    original_name: str
    description: str | None
    input_schema: dict[str, Any]
    enabled: bool


@dataclass(frozen=True)
class DiscoveredResource:
    prefixed_uri: str
    original_uri: str
    name: str | None
    description: str | None
    mime_type: str | None
    enabled: bool


@dataclass(frozen=True)
class DiscoveredPrompt:
    prefixed_name: str
    original_name: str
    description: str | None
    arguments: list[dict[str, Any]]
    enabled: bool


class CapabilityDiscovery:
    """Per-session live-query + cache + preferences reconciliation."""

    def __init__(
        self,
        resource_service: ResourceService,
        supervisor: SubprocessSupervisor,
        preferences: MCPCapabilityPreferenceRepoPort,
        audit: AuditService,
        *,
        cache_ttl_seconds: float = _DEFAULT_CACHE_TTL_SECONDS,
        clock: Any = None,
    ) -> None:
        self._resources = resource_service
        self._supervisor = supervisor
        self._prefs = preferences
        self._audit = audit
        self._ttl = cache_ttl_seconds
        self._clock: Any = clock or time.monotonic
        self._caches: dict[str, _UpstreamCache] = {}

    def _cache_for(self, server_name: str) -> _UpstreamCache:
        return self._caches.setdefault(server_name, _UpstreamCache())

    def _lock_for(self, server_name: str, capability_type: CapabilityType) -> asyncio.Lock:
        cache = self._cache_for(server_name)
        if capability_type not in cache.locks:
            cache.locks[capability_type] = asyncio.Lock()
        return cache.locks[capability_type]

    def _is_fresh(self, fetched_at: float) -> bool:
        return fetched_at > 0 and (self._clock() - fetched_at) < self._ttl

    def invalidate(self, server_name: str, capability_type: CapabilityType | None = None) -> None:
        """Force the next query to bypass the cache for this server / type."""
        cache = self._caches.get(server_name)
        if cache is None:
            return
        if capability_type is None:
            cache.tools = cache.resources = cache.prompts = None
            cache.tools_fetched_at = cache.resources_fetched_at = cache.prompts_fetched_at = 0.0
        else:
            attr, ts_attr = _ATTRS_BY_TYPE[capability_type]
            setattr(cache, attr, None)
            setattr(cache, ts_attr, 0.0)

    async def list_tools(self, server_name: str) -> list[DiscoveredTool]:
        cache = self._cache_for(server_name)
        # CODE-036: fetch the resource row at most once per call and thread it
        # through reconcile + pref-map, instead of each helper independently
        # re-querying (and re-validating) the same row on the cold path.
        resource = None
        async with self._lock_for(server_name, "tool"):
            if cache.tools is None or not self._is_fresh(cache.tools_fetched_at):
                conn = await self._supervisor.get_or_spawn(server_name)
                result = await conn.request("tools/list", {})
                cache.tools = [
                    MCPTool(
                        name=t.name,
                        description=getattr(t, "description", None),
                        input_schema=getattr(t, "inputSchema", None) or {},
                    )
                    for t in getattr(result, "tools", [])
                ]
                cache.tools_fetched_at = self._clock()
                resource = await self._resources.get(ResourceRef("mcp_server", server_name))
                await self._reconcile_preferences(resource, "tool", [t.name for t in cache.tools])

        prefs = await self._build_pref_map(server_name, "tool", resource=resource)
        return [
            DiscoveredTool(
                prefixed_name=prefix_tool(server_name, t.name),
                original_name=t.name,
                description=t.description,
                input_schema=t.input_schema,
                enabled=prefs.get(t.name, True),
            )
            for t in cache.tools
            if prefs.get(t.name, True)
        ]

    async def list_resources(self, server_name: str) -> list[DiscoveredResource]:
        cache = self._cache_for(server_name)
        resource = None
        async with self._lock_for(server_name, "resource"):
            if cache.resources is None or not self._is_fresh(cache.resources_fetched_at):
                conn = await self._supervisor.get_or_spawn(server_name)
                result = await conn.request("resources/list", {})
                cache.resources = [
                    MCPResource(
                        uri=str(getattr(r, "uri", "")),
                        name=getattr(r, "name", None),
                        description=getattr(r, "description", None),
                        mime_type=getattr(r, "mimeType", None),
                    )
                    for r in getattr(result, "resources", [])
                ]
                cache.resources_fetched_at = self._clock()
                resource = await self._resources.get(ResourceRef("mcp_server", server_name))
                await self._reconcile_preferences(
                    resource, "resource", [r.uri for r in cache.resources]
                )

        prefs = await self._build_pref_map(server_name, "resource", resource=resource)
        return [
            DiscoveredResource(
                prefixed_uri=prefix_resource_uri(server_name, r.uri),
                original_uri=r.uri,
                name=r.name,
                description=r.description,
                mime_type=r.mime_type,
                enabled=prefs.get(r.uri, True),
            )
            for r in cache.resources
            if prefs.get(r.uri, True)
        ]

    async def list_prompts(self, server_name: str) -> list[DiscoveredPrompt]:
        cache = self._cache_for(server_name)
        resource = None
        async with self._lock_for(server_name, "prompt"):
            if cache.prompts is None or not self._is_fresh(cache.prompts_fetched_at):
                conn = await self._supervisor.get_or_spawn(server_name)
                result = await conn.request("prompts/list", {})
                cache.prompts = [
                    MCPPrompt(
                        name=p.name,
                        description=getattr(p, "description", None),
                        arguments=[
                            MCPPromptArgument(
                                name=a.name,
                                description=getattr(a, "description", None),
                                required=getattr(a, "required", False),
                            )
                            for a in (getattr(p, "arguments", []) or [])
                        ],
                    )
                    for p in getattr(result, "prompts", [])
                ]
                cache.prompts_fetched_at = self._clock()
                resource = await self._resources.get(ResourceRef("mcp_server", server_name))
                await self._reconcile_preferences(
                    resource, "prompt", [p.name for p in cache.prompts]
                )

        prefs = await self._build_pref_map(server_name, "prompt", resource=resource)
        return [
            DiscoveredPrompt(
                prefixed_name=prefix_prompt(server_name, p.name),
                original_name=p.name,
                description=p.description,
                arguments=[a.model_dump() for a in p.arguments],
                enabled=prefs.get(p.name, True),
            )
            for p in cache.prompts
            if prefs.get(p.name, True)
        ]

    async def _build_pref_map(
        self,
        server_name: str,
        capability_type: CapabilityType,
        *,
        resource: Any = None,
    ) -> dict[str, bool]:
        # CODE-036: reuse a resource row already fetched by the caller on the
        # cold path; only re-query on a cache hit (where none was fetched). The
        # preference rows themselves are always read fresh so enable/disable
        # toggles take effect immediately, independent of the list cache TTL.
        if resource is None:
            resource = await self._resources.get(ResourceRef("mcp_server", server_name))
        prefs = await self._prefs.list_for(resource.id, capability_type)
        return {p.capability_key: p.enabled for p in prefs}

    async def _reconcile_preferences(
        self,
        resource: Any,
        capability_type: CapabilityType,
        current_keys: list[str],
    ) -> None:
        """Insert new keys at the server's default; touch last_seen for existing.

        Missing keys are NOT deleted — this preserves any disable intent the
        user expressed for a capability that temporarily disappeared upstream.

        Implementation: one batched UPDATE for existing rows and one batched
        INSERT … ON CONFLICT DO NOTHING for net-new rows, both inside a single
        session (CODE-004 fixed the previous per-key-per-session N+1 plus the
        check-then-insert race that could trip the UniqueConstraint when two
        sessions reconciled the same upstream concurrently).

        CODE-036: takes the already-fetched ``resource`` so the cold path does
        not re-query + re-validate the same row that the caller just loaded.
        """
        config = MCPServerConfig.model_validate(resource.config)
        default_enabled = config.auto_enable_new_capabilities
        now = datetime.now(tz=UTC)

        new_keys = await self._prefs.reconcile(
            resource.id,
            capability_type,
            current_keys,
            default_enabled=default_enabled,
            when=now,
        )

        for key in new_keys:
            await self._audit.record(
                AuditEventType.CAPABILITY_FIRST_SEEN.value,
                ref=resource.ref,
                actor="system",
                details={
                    "capability_type": capability_type,
                    "key": key,
                    "default_enabled": default_enabled,
                },
            )
