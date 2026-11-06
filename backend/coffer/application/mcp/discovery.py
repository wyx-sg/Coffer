"""Capability discovery for MCP gateway sessions.

The person's switches are stored per capability key; the lists themselves come
from the upstream. A session with a catalogue (the gateway's) answers a list
from what the server listed last on this machine, under the same config, and
starts the server only when a call needs it; a server never listed here, or
one whose config changed since, is asked live, and so is one the session is
already connected to. Every live answer is saved for the next session (ADR
session-subprocess-model). A short in-process cache sits in front of both.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

import mcp.types as mcp_types
from mcp import MCPError

from coffer.application.mcp.discovery_parse import (
    config_hash,
    parse_prompts,
    parse_resources,
    parse_tools,
)
from coffer.application.mcp.ports import MCPCapabilityPreferenceRepoPort, McpCataloguePort
from coffer.application.mcp.supervisor import SubprocessSupervisor, UpstreamHealth
from coffer.application.resource_service import ResourceService
from coffer.domain.errors import UpstreamTimeout, UpstreamUnavailable
from coffer.domain.mcp.capability import (
    CapabilityType,
    MCPPrompt,
    MCPResource,
    MCPTool,
)
from coffer.domain.mcp.namespace import prefix_prompt, prefix_resource_uri, prefix_tool

_DEFAULT_CACHE_TTL_SECONDS = 60.0


def _is_method_not_found(exc: Exception) -> bool:
    """True for the JSON-RPC -32601 reply a capability-less upstream sends for
    an unsupported ``*/list`` (e.g. a tools-only server answering prompts/list).
    That is a legitimate 'no such capability', not a broken connection."""
    return isinstance(exc, MCPError) and exc.code == mcp_types.METHOD_NOT_FOUND


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
    annotations: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None


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
    """Per-session live-query + cache + preferences reconciliation.

    Keyed throughout on the server's NAME, because a capability's public
    identity on the MCP wire is the namespaced ``<server>__<tool>`` this class
    builds, and that namespace is the label. The name is resolved to the row
    once per cold path, and everything persisted from there on — the switches
    and seen-times this reconciles — is keyed on the server's uid.
    """

    def __init__(
        self,
        resource_service: ResourceService,
        supervisor: SubprocessSupervisor,
        preferences: MCPCapabilityPreferenceRepoPort,
        *,
        cache_ttl_seconds: float = _DEFAULT_CACHE_TTL_SECONDS,
        clock: Any = None,
        catalogue: McpCataloguePort | None = None,
    ) -> None:
        self._resources = resource_service
        self._supervisor = supervisor
        self._prefs = preferences
        self._ttl = cache_ttl_seconds
        self._clock: Any = clock or time.monotonic
        self._caches: dict[str, _UpstreamCache] = {}
        self._catalogue = catalogue

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

    async def list_tools(
        self, server_name: str, *, include_disabled: bool = False
    ) -> list[DiscoveredTool]:
        cache = self._cache_for(server_name)
        # Fetch the resource row at most once per call and thread it
        # through reconcile + pref-map, instead of each helper independently
        # re-querying (and re-validating) the same row on the cold path.
        resource = None
        async with self._lock_for(server_name, "tool"):
            if cache.tools is None or not self._is_fresh(cache.tools_fetched_at):
                resource, cache.tools = await self._listed(
                    server_name, "tool", "tools/list", parse_tools, MCPTool, key=lambda t: t.name
                )
                cache.tools_fetched_at = self._clock()

        prefs = await self._build_pref_map(server_name, "tool", resource=resource)
        return [
            DiscoveredTool(
                prefixed_name=prefix_tool(server_name, t.name),
                original_name=t.name,
                description=t.description,
                input_schema=t.input_schema,
                enabled=prefs.get(t.name, True),
                annotations=t.annotations,
                output_schema=t.output_schema,
            )
            for t in cache.tools
            if include_disabled or prefs.get(t.name, True)
        ]

    async def list_resources(
        self, server_name: str, *, include_disabled: bool = False
    ) -> list[DiscoveredResource]:
        cache = self._cache_for(server_name)
        resource = None
        async with self._lock_for(server_name, "resource"):
            if cache.resources is None or not self._is_fresh(cache.resources_fetched_at):
                # An upstream that implements only tools replies -32601 to
                # resources/list: it has no resources, which is not an error.
                resource, cache.resources = await self._listed(
                    server_name,
                    "resource",
                    "resources/list",
                    parse_resources,
                    MCPResource,
                    key=lambda r: r.uri,
                    absent_ok=True,
                )
                cache.resources_fetched_at = self._clock()

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
            if include_disabled or prefs.get(r.uri, True)
        ]

    async def list_prompts(
        self, server_name: str, *, include_disabled: bool = False
    ) -> list[DiscoveredPrompt]:
        cache = self._cache_for(server_name)
        resource = None
        async with self._lock_for(server_name, "prompt"):
            if cache.prompts is None or not self._is_fresh(cache.prompts_fetched_at):
                resource, cache.prompts = await self._listed(
                    server_name,
                    "prompt",
                    "prompts/list",
                    parse_prompts,
                    MCPPrompt,
                    key=lambda p: p.name,
                    absent_ok=True,
                )
                cache.prompts_fetched_at = self._clock()

        prefs = await self._build_pref_map(server_name, "prompt", resource=resource)
        return [
            DiscoveredPrompt(
                prefixed_name=prefix_prompt(server_name, p.name),
                original_name=p.name,
                description=p.description,
                arguments=[a.model_dump(by_alias=True) for a in p.arguments],
                enabled=prefs.get(p.name, True),
            )
            for p in cache.prompts
            if include_disabled or prefs.get(p.name, True)
        ]

    async def _listed(
        self,
        server_name: str,
        capability_type: CapabilityType,
        method: str,
        parse: Callable[[Any], list[Any]],
        model: Any,
        *,
        key: Callable[[Any], str],
        absent_ok: bool = False,
    ) -> tuple[Any, list[Any]]:
        """The server's row and its list: saved when it can be, else live.

        Saved: this machine has a list the server gave under the config it has
        now, and the session is not connected to it (a live connection is
        cheap to ask, and its ``list_changed`` notifications are what keep a
        list current). Live otherwise: the answer is reconciled with the
        switches and saved for the next session."""
        resource = await self._resources.get_by_name("mcp_server", server_name)
        digest = config_hash(resource.config)
        if (
            self._catalogue is not None
            and self._supervisor.health(server_name) is not UpstreamHealth.HEALTHY
        ):
            saved = await self._catalogue.load(resource.uid, capability_type)
            if saved is not None and saved[0] == digest:
                try:
                    return resource, [model.model_validate(item) for item in saved[1]]
                except ValueError:
                    pass  # a list saved in another shape: ask the server
        try:
            items = parse(await self._request_self_heal(server_name, method, {}))
        except MCPError as exc:
            if not (absent_ok and exc.code == mcp_types.METHOD_NOT_FOUND):
                raise
            items = []
        else:
            await self._reconcile_preferences(resource, capability_type, [key(i) for i in items])
        if self._catalogue is not None:
            await self._catalogue.save(
                resource.uid, capability_type, digest, [i.model_dump(mode="json") for i in items]
            )
        return resource, items

    async def request(self, server_name: str, method: str, params: dict[str, Any]) -> Any:
        """One upstream request for the server page's previews (``resources/read``,
        ``prompts/get``), on the same healed connection as the listings. An error
        the upstream answers with (a missing argument, an unknown URI) is its
        answer, raised as is, and never costs the connection."""
        return await self._request_self_heal(server_name, method, params, answered_ok=True)

    async def _request_self_heal(
        self, server_name: str, method: str, params: dict[str, Any], *, answered_ok: bool = False
    ) -> Any:
        """Issue an upstream ``*/list`` request, healing a stale reused
        connection in place.

        The process-wide management supervisor caches one connection per
        upstream and keeps handing it back as HEALTHY. That connection can go
        dead under it — the MCP session expires, the upstream restarts, the
        socket is dropped — and the cached entry never notices. The gateway
        request path evicts a connection the moment a call on it fails
        (``gateway_handlers._invoke``); the discovery path had no such healing,
        so a dead connection produced a bare 500 / empty list until daemon
        restart, while Test connection (which builds a fresh connection) stayed
        green and Refresh (which only clears the data cache) did nothing.

        Mirror the gateway here: on any failure other than METHOD_NOT_FOUND (a
        real 'no such capability') or a timeout, evict the broken connection
        and retry once on a freshly spawned one. A still-failing retry is
        normalised to UpstreamUnavailable so the management surface returns
        503 UPSTREAM_UNAVAILABLE instead of leaking a 500.
        """
        conn = await self._supervisor.get_or_spawn(server_name)
        try:
            return await conn.request(method, params)
        except UpstreamTimeout:
            raise
        except Exception as first_exc:
            if _is_method_not_found(first_exc) or (answered_ok and isinstance(first_exc, MCPError)):
                raise
            await self._supervisor.evict(server_name)
            conn = await self._supervisor.get_or_spawn(server_name)
            try:
                return await conn.request(method, params)
            except (UpstreamTimeout, UpstreamUnavailable):
                raise
            except Exception as retry_exc:
                if _is_method_not_found(retry_exc):
                    raise
                raise UpstreamUnavailable(
                    f"{server_name!r} {method} failed after reconnect: {type(retry_exc).__name__}"
                ) from retry_exc

    async def _build_pref_map(
        self,
        server_name: str,
        capability_type: CapabilityType,
        *,
        resource: Any = None,
    ) -> dict[str, bool]:
        # Reuse a resource row already fetched by the caller on the
        # cold path; only re-query on a cache hit (where none was fetched). The
        # preference rows themselves are always read fresh so enable/disable
        # toggles take effect immediately, independent of the list cache TTL.
        if resource is None:
            resource = await self._resources.get_by_name("mcp_server", server_name)
        prefs = await self._prefs.list_for(resource.uid, capability_type)
        return {p.capability_key: p.enabled for p in prefs}

    async def _reconcile_preferences(
        self,
        resource: Any,
        capability_type: CapabilityType,
        current_keys: list[str],
    ) -> None:
        """Insert newly seen keys enabled; touch last_seen for existing ones.

        Missing keys are NOT deleted — this preserves any disable intent the
        user expressed for a capability that temporarily disappeared upstream.

        Implementation: one batched UPDATE for existing rows and one batched
        INSERT … ON CONFLICT DO NOTHING for net-new rows, both inside a single
        session (this replaced the previous per-key-per-session N+1 plus the
        check-then-insert race that could trip the UniqueConstraint when two
        sessions reconciled the same upstream concurrently).

        Takes the already-fetched ``resource`` so the cold path does
        not re-query the same row that the caller just loaded.
        """
        await self._prefs.reconcile(
            resource.uid,
            capability_type,
            current_keys,
            default_enabled=True,
            when=datetime.now(tz=UTC),
        )
