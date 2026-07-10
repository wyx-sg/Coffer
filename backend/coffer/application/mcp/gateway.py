"""MCPGatewaySession — per-downstream-client routing brain.

One instance per downstream MCP client connection. Owns:
- A SubprocessSupervisor (manages per-upstream connections)
- A CapabilityDiscovery (caches lists, reconciles preferences)
- A queue of upstream notifications to forward downstream

Invocation handlers (tools/call, resources/read, prompts/get) live in
`gateway_handlers` to keep this module under 400 LOC.

Server-initiated request plumbing (T-061 sampling, T-062 roots) lives in
`gateway_server_requests` for the same reason. The pure envelope-parsing
helpers (launch-cwd extraction, upstream-notification method/params parsing)
live in `gateway_parsing`.

For the spec's "upstream tool list changes mid-session" scenario, the
session subscribes to each upstream's notification stream (via
`UpstreamConnection.on_notification`) and forwards the relevant
list-changed messages downstream while invalidating the discovery
cache.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from coffer.application.builtin_tools import (
    BuiltinToolRegistry,
)
from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.mcp.gateway_aggregate_lists import (
    list_prompts_across,
    list_resources_across,
    list_tools_across,
)
from coffer.application.mcp.gateway_builtin import (
    append_builtin_tools,
    dispatch_builtin_tool,
    dispatch_tool_search,
    inject_session_cwd,
)
from coffer.application.mcp.gateway_handlers import (
    handle_prompts_get,
    handle_resources_read,
    handle_tools_call,
)
from coffer.application.mcp.gateway_parsing import (
    _extract_agent,
    _extract_cwd,
    _extract_method,
    _extract_params,
)
from coffer.application.mcp.gateway_server_requests import (
    ServerRequestRegistry,
    build_list_roots_callback,
    build_sampling_callback,
)
from coffer.application.mcp.gateway_tool_search import TOOL_SEARCH_NAME
from coffer.application.mcp.ports import (
    MCPCapabilityPreferenceRepoPort,
    MCPInvocationRepoPort,
)
from coffer.application.mcp.supervisor import SubprocessSupervisor
from coffer.application.resource_service import ResourceService
from coffer.domain.errors import UpstreamUnavailable
from coffer.domain.mcp.namespace import prefix_resource_uri
from coffer.domain.scope import agent_in_scope, machine_in_scope

_logger = logging.getLogger(__name__)


# Downstream-bound notification: a dict that gets serialised as JSON-RPC
DownstreamNotification = dict[str, Any]
NotificationSink = Callable[[DownstreamNotification], Awaitable[None]]


# MCP server capabilities coffer declares to clients.
_COFFER_SERVER_CAPABILITIES: dict[str, Any] = {
    "tools": {"listChanged": True},
    "resources": {"listChanged": True, "subscribe": False},
    "prompts": {"listChanged": True},
}


class MCPGatewaySession:
    """Per-downstream-client gateway routing."""

    def __init__(
        self,
        session_id: str | None,
        resource_service: ResourceService,
        supervisor: SubprocessSupervisor,
        discovery: CapabilityDiscovery,
        preferences: MCPCapabilityPreferenceRepoPort,
        invocations: MCPInvocationRepoPort,
        downstream_sink: NotificationSink | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
        on_dispose: Callable[[], None] | None = None,
        builtin_tools: BuiltinToolRegistry | None = None,
        embedder_provider: Callable[[], Awaitable[Any | None]] | None = None,
        machine_id: Callable[[], Awaitable[str | None]] | None = None,
    ) -> None:
        self.id = session_id or str(uuid.uuid4())
        self._resources = resource_service
        self._supervisor = supervisor
        self._discovery = discovery
        self._prefs = preferences
        self._invocations = invocations
        self._downstream_sink = downstream_sink
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        # ADR-045 machine axis (Task 8): optional provider resolving this
        # machine's sync identity, resolved once and cached per session
        # (mirroring ChannelRuntime — channel/runtime.py:181-186). None (the
        # default) means no provider is wired — legacy behavior, no filtering.
        self._machine_id = machine_id
        self._machine_id_value: str | None = None
        # ADR-045 agent axis (Task 9): the session's bound agent identity, set
        # from the shim's self-reported ``--agent`` name on the ``initialize``
        # handshake (params._meta["coffer/agent"], see handle_initialize).
        # None when the shim was launched without one (pre-Task-9 install, or
        # an unnamed launch) — the agent-axis filter is then a no-op.
        self._session_agent: str | None = None
        # CODE-035: called once when the session is disposed so the composition
        # root can drop this session's entry from its supervisor registry
        # (otherwise disposed-but-registered supervisors accumulate for the
        # daemon's lifetime and the on_delete hook walks dead ones).
        self._on_dispose = on_dispose
        self._builtin = builtin_tools or BuiltinToolRegistry()
        self._embedder_provider = embedder_provider  # semantic search_tools; None → BM25
        self._initialized = False
        # FR-004: the agent's launch cwd, reported by the shim at the
        # ``initialize`` handshake (params._meta["coffer/cwd"]). Threaded into
        # memory built-in tool calls so project-scope resolution works. Falls
        # back to the daemon's own cwd when the client omits it.
        self._session_cwd: str | None = None
        # Track which servers we've subscribed to notifications on so we
        # only attach the handler once per (session, server) pair.
        self._notification_subscriptions: set[str] = set()
        # CODE-L4: the event loop holds tasks weakly — an un-referenced
        # ensure_future() task can be garbage-collected mid-flight, silently
        # dropping an upstream notification. Hold strong refs until done.
        self._notification_tasks: set[asyncio.Task[None]] = set()
        # Downstream client capabilities declared during initialize (T-061/T-062).
        self._client_capabilities: dict[str, Any] = {}
        # Server-initiated request bookkeeping (T-061 sampling, T-062 roots).
        self._server_request_registry = ServerRequestRegistry()
        # Pre-build SDK callbacks so we can register them on connection objects.
        self._sampling_callback = build_sampling_callback(
            self._server_request_registry,
            lambda: self._downstream_sink,
            lambda: self._client_capabilities,
            self.id,
        )
        self._list_roots_callback = build_list_roots_callback(
            self._server_request_registry,
            lambda: self._downstream_sink,
            self.id,
        )

    def set_downstream_sink(self, sink: NotificationSink) -> None:
        """Called by the session runner once the downstream wire is open."""
        self._downstream_sink = sink

    # --- Initialize ---

    async def handle_initialize(
        self,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Respond to the client's initialize request with coffer's server capabilities."""
        # Record the downstream client's capabilities so we can gate server-initiated
        # requests appropriately (T-061: sampling capability check).
        self._client_capabilities = params.get("capabilities", {}) or {}
        self._session_cwd = _extract_cwd(params)
        # ADR-045 agent axis (Task 9): the shim's self-reported `--agent`
        # identity, when it stamped one (params._meta["coffer/agent"]).
        self._session_agent = _extract_agent(params)
        self._initialized = True
        return {
            "protocolVersion": "2025-06-18",
            "capabilities": _COFFER_SERVER_CAPABILITIES,
            "serverInfo": {
                "name": "coffer",
                "version": "0.1.0",
            },
        }

    # --- Request dispatch ---

    async def handle_request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Top-level dispatcher used by the protocol surface."""
        params = params or {}
        if method == "tools/list":
            return await self._handle_tools_list()
        if method == "tools/call":
            return await self._handle_tools_call(params)
        if method == "resources/list":
            return await self._handle_resources_list()
        if method == "resources/read":
            return await self._handle_resources_read(params)
        if method == "prompts/list":
            return await self._handle_prompts_list()
        if method == "prompts/get":
            return await self._handle_prompts_get(params)
        raise UpstreamUnavailable(f"method not supported by gateway: {method!r}")

    def handle_response_from_downstream(self, envelope: dict[str, Any]) -> bool:
        """Route an incoming JSON-RPC response to a pending server-initiated request.

        Returns True if matched and consumed; False if the envelope should be
        treated as a normal client request.
        """
        return self._server_request_registry.handle_response(envelope)

    async def _local_machine_id(self) -> str | None:
        if self._machine_id is None:
            return None
        if self._machine_id_value is None:
            self._machine_id_value = await self._machine_id()
        return self._machine_id_value

    async def _enabled_mcp_servers(self) -> list[str]:
        # Push the enabled=true filter to SQL so we don't materialise rows
        # we'll throw away (CODE-021).
        local = await self._local_machine_id()
        resources = await self._resources.list(kind="mcp_server", enabled=True)
        enabled_names: list[str] = []
        for r in resources:
            if local is not None and not machine_in_scope(r.scope, local):
                continue
            if local is not None and not agent_in_scope(r.scope, local, self._session_agent):
                continue
            enabled_names.append(r.name)
        return enabled_names

    async def _ensure_subscribed(self, server_name: str) -> None:
        """Attach notification + server-request handlers to the upstream connection lazily."""
        if server_name in self._notification_subscriptions:
            return
        try:
            conn = await self._supervisor.get_or_spawn(server_name)
        except UpstreamUnavailable:
            return

        def _spawn_notification_task(notif: Any) -> asyncio.Task[None]:
            task = asyncio.ensure_future(self._on_upstream_notification(server_name, notif))
            self._notification_tasks.add(task)
            task.add_done_callback(self._notification_tasks.discard)
            return task

        conn.on_notification(_spawn_notification_task)
        # T-061/T-062: register callbacks so the SDK can handle server-initiated
        # sampling and roots requests from this upstream.
        conn.on_sampling_request(self._sampling_callback)
        conn.on_roots_request(self._list_roots_callback)
        self._notification_subscriptions.add(server_name)

    # --- tools/list, resources/list, prompts/list ---
    # Aggregate fan-out lives in gateway_aggregate_lists.py — see that
    # module's header for the per-server budget + parallelism rationale.

    async def _handle_tools_list(self) -> dict[str, Any]:
        result = await list_tools_across(
            self._discovery, self._ensure_subscribed, await self._enabled_mcp_servers()
        )
        append_builtin_tools(result["tools"], self._builtin)
        return result

    async def _handle_resources_list(self) -> dict[str, Any]:
        return await list_resources_across(
            self._discovery, self._ensure_subscribed, await self._enabled_mcp_servers()
        )

    async def _handle_prompts_list(self) -> dict[str, Any]:
        return await list_prompts_across(
            self._discovery, self._ensure_subscribed, await self._enabled_mcp_servers()
        )

    # --- tools/call, resources/read, prompts/get (delegated to gateway_handlers) ---

    def _on_upstream_evicted(self, server_name: str) -> None:
        """Discard the subscription entry so the next call re-registers the
        notification callback on the fresh connection spawned by the supervisor.

        Called by the invocation handlers immediately after supervisor.evict().
        """
        self._notification_subscriptions.discard(server_name)

    async def _handle_tools_call(self, params: dict[str, Any]) -> Any:
        name = str(params.get("name") or "")
        if name == TOOL_SEARCH_NAME:
            listed = await list_tools_across(
                self._discovery, self._ensure_subscribed, await self._enabled_mcp_servers()
            )
            embedder = await self._embedder_provider() if self._embedder_provider else None
            return await dispatch_tool_search(
                params=params,
                aggregated_tools=listed["tools"],
                invocations=self._invocations,
                session_id=self.id,
                clock=self._clock,
                embedder=embedder,
            )
        if self._builtin.is_builtin(name):
            params = self._inject_session_cwd(name, params)
            return await dispatch_builtin_tool(
                prefixed_name=name,
                params=params,
                builtin=self._builtin,
                invocations=self._invocations,
                session_id=self.id,
                clock=self._clock,
            )
        return await handle_tools_call(
            params,
            resources=self._resources,
            supervisor=self._supervisor,
            prefs=self._prefs,
            invocations=self._invocations,
            session_id=self.id,
            clock=self._clock,
            ensure_subscribed=self._ensure_subscribed,
            on_evict=self._on_upstream_evicted,
        )

    def _inject_session_cwd(self, prefixed_name: str, params: dict[str, Any]) -> dict[str, Any]:
        return inject_session_cwd(self._builtin, prefixed_name, params, self._session_cwd)

    async def _handle_resources_read(self, params: dict[str, Any]) -> Any:
        return await handle_resources_read(
            params,
            resources=self._resources,
            supervisor=self._supervisor,
            prefs=self._prefs,
            invocations=self._invocations,
            session_id=self.id,
            clock=self._clock,
            ensure_subscribed=self._ensure_subscribed,
            on_evict=self._on_upstream_evicted,
        )

    async def _handle_prompts_get(self, params: dict[str, Any]) -> Any:
        return await handle_prompts_get(
            params,
            resources=self._resources,
            supervisor=self._supervisor,
            prefs=self._prefs,
            invocations=self._invocations,
            session_id=self.id,
            clock=self._clock,
            ensure_subscribed=self._ensure_subscribed,
            on_evict=self._on_upstream_evicted,
        )

    # --- Upstream → downstream notification forwarding ---

    async def _on_upstream_notification(self, server_name: str, notification: Any) -> None:
        """Handle one incoming notification from `server_name`.

        Invalidates the appropriate discovery cache slice + forwards
        downstream (with URI rewriting for resources/updated).
        """
        # The notification object's shape varies by SDK version; we look at
        # `method` (the JSON-RPC method name) and `params` defensively.
        method = _extract_method(notification)
        if method is None:
            return

        if method == "notifications/tools/list_changed":
            self._discovery.invalidate(server_name, "tool")
            await self._send_downstream({"method": method, "params": {}})
        elif method == "notifications/resources/list_changed":
            self._discovery.invalidate(server_name, "resource")
            await self._send_downstream({"method": method, "params": {}})
        elif method == "notifications/prompts/list_changed":
            self._discovery.invalidate(server_name, "prompt")
            await self._send_downstream({"method": method, "params": {}})
        elif method == "notifications/resources/updated":
            raw_params = _extract_params(notification) or {}
            original_uri = raw_params.get("uri")
            if original_uri:
                raw_params = {**raw_params, "uri": prefix_resource_uri(server_name, original_uri)}
            await self._send_downstream({"method": method, "params": raw_params})
        # Everything else (notifications/message, notifications/progress) is
        # dropped on the floor — out of scope for this task (T060 adds progress).

    async def _send_downstream(self, payload: DownstreamNotification) -> None:
        if self._downstream_sink is None:
            return
        try:
            await self._downstream_sink(payload)
        except Exception as e:
            _logger.warning("mcp.gateway.downstream_sink_failed", extra={"error": str(e)})

    # --- Dispose ---

    async def dispose(self) -> None:
        """Close every owned upstream + drop all state."""
        # Cancel any in-flight server-initiated requests
        self._server_request_registry.cancel_all()

        await self._supervisor.dispose()
        self._notification_subscriptions.clear()
        self._initialized = False
        # CODE-035: let the composition root drop its registry entry last, after
        # the supervisor is fully disposed.
        if self._on_dispose is not None:
            with contextlib.suppress(Exception):
                self._on_dispose()
