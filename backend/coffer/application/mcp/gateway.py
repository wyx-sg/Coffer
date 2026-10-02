"""MCPGatewaySession — per-downstream-client routing brain.

One instance per downstream MCP client connection. Owns:
- A SubprocessSupervisor (manages per-upstream connections)
- A CapabilityDiscovery (caches lists, reconciles preferences)
- A queue of upstream notifications to forward downstream

Invocation handlers (tools/call, resources/read, prompts/get) live in
`gateway_handlers` to keep this module under 400 LOC, and the tools/list
composition — aggregate, plus built-ins, minus what tiering hides — lives in
`gateway_tools_list`.

Server-initiated request plumbing (sampling and roots) lives in
`gateway_server_requests` for the same reason. The pure envelope-parsing
helpers (launch-cwd extraction, upstream-notification method/params parsing)
live in `gateway_parsing`. The per-agent scope filter for the
enabled-server list lives in `gateway_scope`.

For the spec's "upstream tool list changes mid-session" scenario, the
session subscribes to each upstream's notification stream (via
`UpstreamConnectionPort.on_notification`) and forwards the relevant
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
from coffer.application.mcp.custom_tool_ports import ToolReachRepoPort
from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.mcp.gateway_aggregate_lists import (
    list_prompts_across,
    list_resources_across,
)
from coffer.application.mcp.gateway_builtin import (
    agent_actor_label,
    dispatch_builtin_tool,
    inject_session_context,
    run_tool_search,
)
from coffer.application.mcp.gateway_handlers import (
    handle_prompts_get,
    handle_resources_read,
    handle_tools_call,
)
from coffer.application.mcp.gateway_instructions import build_initialize_result
from coffer.application.mcp.gateway_notifications import forward_upstream_notification
from coffer.application.mcp.gateway_parsing import (
    _extract_agent_uid,
    _extract_cwd,
)
from coffer.application.mcp.gateway_recovery import DegradedTracker
from coffer.application.mcp.gateway_scope import enabled_mcp_servers, visible_mcp_servers
from coffer.application.mcp.gateway_server_requests import (
    ServerRequestRegistry,
    build_session_callbacks,
)
from coffer.application.mcp.gateway_tool_gate import hidden_tool_names
from coffer.application.mcp.gateway_tool_search import TOOL_SEARCH_NAME
from coffer.application.mcp.gateway_tools_list import build_tools_listing
from coffer.application.mcp.ports import (
    MCPCapabilityPreferenceRepoPort,
    MCPInvocationRepoPort,
)
from coffer.application.mcp.saved_tools import saved_hidden_count
from coffer.application.mcp.supervisor import SubprocessSupervisor
from coffer.application.mcp.tiering_config import TieringConfig, load_tiering_config
from coffer.application.mcp.tool_exposure import exposure_overrides
from coffer.application.resource_service import ResourceService
from coffer.application.runtime.supervisor import spawn
from coffer.domain.errors import UpstreamUnavailable

_logger = logging.getLogger(__name__)


# Downstream-bound notification: a dict that gets serialised as JSON-RPC
DownstreamNotification = dict[str, Any]
NotificationSink = Callable[[DownstreamNotification], Awaitable[None]]


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
        tiering: TieringConfig | None = None,
        tool_reach: ToolReachRepoPort | None = None,
    ) -> None:
        self.id = session_id or str(uuid.uuid4())
        self._tool_reach = tool_reach  # custom tools' reach overrides (gateway_tool_gate)
        self._resources = resource_service
        self._supervisor = supervisor
        self._discovery = discovery
        self._prefs = preferences
        self._invocations = invocations
        self._downstream_sink = downstream_sink
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        # Per-agent scope: the session's bound agent **uid** (a ``scope`` holds
        # uids; ADR identity-is-the-uid-inside-the-file), from the shim's
        # ``--agent-uid`` on ``initialize`` (params._meta["coffer/agent-uid"]).
        # None when it reported nothing: such a session sees only unscoped servers.
        self._session_agent_uid: str | None = None
        # Called once on dispose so the composition root drops this session's
        # supervisor from its registry (else dead ones accumulate).
        self._on_dispose = on_dispose
        # ``is not None``, not ``or``: a registry with every tool off is falsy.
        self._builtin = builtin_tools if builtin_tools is not None else BuiltinToolRegistry()
        # Tool tiering: how much of the catalogue this session lists (None = read env).
        self._tiering = tiering or load_tiering_config()
        # Upstream tools left unlisted by tiering, for the instructions text:
        # estimated from the saved tool lists at ``initialize`` and replaced by
        # the real count at every ``tools/list``.
        self.last_hidden_count = 0
        # The agent's launch cwd from the shim's handshake (params._meta["coffer/cwd"]),
        # threaded into built-in tool calls; no spec states it any more (its
        # requirement went with the per-project store), the shim still stamps it.
        self._session_cwd: str | None = None
        # Servers whose notifications this session already subscribed to.
        self._notification_subscriptions: set[str] = set()
        # The loop holds tasks weakly; strong refs keep an upstream
        # notification from being garbage-collected mid-flight.
        self._notification_tasks: set[asyncio.Task[None]] = set()
        # Tool tiering: servers whose discovery failed on the last tools/list. The
        # client caches tools/list and no list_changed can arrive from a server
        # that never connected, so the tracker retries them itself.
        self._degraded = DegradedTracker(discovery, self._send_downstream)
        # Downstream client capabilities declared during initialize.
        self._client_capabilities: dict[str, Any] = {}
        # Server-initiated request bookkeeping (sampling and roots).
        self._server_request_registry = ServerRequestRegistry()
        # Pre-build SDK callbacks so we can register them on connection objects.
        callbacks = build_session_callbacks(
            self._server_request_registry,
            lambda: self._downstream_sink,
            lambda: self._client_capabilities,
            self.id,
        )
        self._sampling_callback = callbacks.sampling
        self._list_roots_callback = callbacks.list_roots

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
        # requests appropriately (the sampling capability check).
        self._client_capabilities = params.get("capabilities", {}) or {}
        self._session_cwd = _extract_cwd(params)
        # The identity scope is evaluated against: the shim's self-reported
        # agent uid, when it stamped one (params._meta["coffer/agent-uid"]).
        self._session_agent_uid = _extract_agent_uid(params)
        # The instructions field is the only channel into the client's system
        # prompt and is read before the first tools/list, so the unlisted count
        # comes from the saved tool lists; it names only the built-ins listed now.
        self.last_hidden_count = await saved_hidden_count(
            self._resources,
            self._session_agent_uid,
            self._tool_reach,
            prefs=self._prefs,
            invocations=self._invocations,
            config=self._tiering,
            clock=self._clock,
        )
        return build_initialize_result(
            hidden_count=self.last_hidden_count,
            tools=[tool.name for tool in self._builtin.list()],
            memory_root=self._builtin.directory("memory"),
        )

    # --- Request dispatch ---

    async def handle_request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Top-level dispatcher used by the protocol surface."""
        params = params or {}
        if method == "tools/list":
            return await self._handle_tools_list()
        if method == "tools/call":
            return await self._handle_tools_call(params)
        if method == "resources/list":
            return await list_resources_across(
                self._discovery, self._ensure_subscribed, await self._enabled_mcp_servers()
            )
        if method == "resources/read":
            return await self._dispatch_handler(handle_resources_read, params)
        if method == "prompts/list":
            return await list_prompts_across(
                self._discovery, self._ensure_subscribed, await self._enabled_mcp_servers()
            )
        if method == "prompts/get":
            return await self._dispatch_handler(handle_prompts_get, params)
        raise UpstreamUnavailable(f"method not supported by gateway: {method!r}")

    def handle_response_from_downstream(self, envelope: dict[str, Any]) -> bool:
        """Route an incoming JSON-RPC response to a pending server-initiated request.

        Returns True if matched and consumed; False if the envelope should be
        treated as a normal client request.
        """
        return self._server_request_registry.handle_response(envelope)

    @property
    def _log_ctx(self) -> dict[str, Any]:
        """What every path that records an invocation needs to write its row.

        ``session_agent_uid`` is read at call time, so a row carries the uid the
        session reported on ``initialize`` (or ``None`` when it reported none).
        """
        return {
            "invocations": self._invocations,
            "session_id": self.id,
            "session_agent_uid": self._session_agent_uid,
            "clock": self._clock,
        }

    async def _enabled_mcp_servers(self) -> list[str]:
        return await enabled_mcp_servers(self._resources, self._session_agent_uid)

    async def _servers_and_hidden(self) -> tuple[list[str], frozenset[str], dict[str, str]]:
        """Visible server names, tools hidden from this agent, per-tool exposure overrides."""
        rows = await visible_mcp_servers(self._resources, self._session_agent_uid)
        hidden = await hidden_tool_names(rows, self._session_agent_uid, self._tool_reach)
        return [r.name for r in rows], hidden, await exposure_overrides(self._prefs, rows)

    async def _ensure_subscribed(self, server_name: str) -> None:
        """Attach notification + server-request handlers to the upstream connection lazily."""
        if server_name in self._notification_subscriptions:
            return
        try:
            conn = await self._supervisor.get_or_spawn(server_name)
        except UpstreamUnavailable:
            return

        def _spawn_notification_task(notif: Any) -> asyncio.Task[None]:
            coro = self._on_upstream_notification(server_name, notif)
            task = spawn(coro, name=f"mcp-upstream-notification:{server_name}")
            self._notification_tasks.add(task)
            task.add_done_callback(self._notification_tasks.discard)
            return task

        conn.on_notification(_spawn_notification_task)
        # Register callbacks so the SDK can handle server-initiated
        # sampling and roots requests from this upstream.
        conn.on_sampling_request(self._sampling_callback)
        conn.on_roots_request(self._list_roots_callback)
        self._notification_subscriptions.add(server_name)

    @property
    def degraded_servers(self) -> set[str]:
        """Servers whose tools are missing from the last listing (tool tiering)."""
        return self._degraded.servers

    async def recover_degraded_now(self) -> bool:
        """Re-discover degraded servers once; True if any recovered."""
        return await self._degraded.recover_now()

    # --- tools/list, resources/list, prompts/list ---
    # Aggregate fan-out lives in gateway_aggregate_lists.py — see that
    # module's header for the per-server budget + parallelism rationale.

    async def _handle_tools_list(self) -> dict[str, Any]:
        servers, hidden, exposure = await self._servers_and_hidden()
        listing = await build_tools_listing(
            discovery=self._discovery,
            ensure_subscribed=self._ensure_subscribed,
            servers=servers,
            hidden=hidden,
            exposure=exposure,
            builtin=self._builtin,
            invocations=self._invocations,
            tiering=self._tiering,
            clock=self._clock,
            degraded=self._degraded,
        )
        self.last_hidden_count = listing.hidden_count
        return {"tools": listing.tools}

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
            servers, hidden, exposure = await self._servers_and_hidden()
            return await run_tool_search(
                params,
                exposure=exposure,
                discovery=self._discovery,
                ensure_subscribed=self._ensure_subscribed,
                servers=servers,
                hidden=hidden,
                **self._log_ctx,
            )
        if self._builtin.is_builtin(name):
            params = await self._inject_session_context(name, params)
            return await dispatch_builtin_tool(
                prefixed_name=name,
                params=params,
                builtin=self._builtin,
                **self._log_ctx,
            )
        return await self._dispatch_handler(handle_tools_call, params)

    async def _inject_session_context(
        self, prefixed_name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        return inject_session_context(
            self._builtin,
            prefixed_name,
            params,
            session_cwd=self._session_cwd,
            agent_label=await agent_actor_label(self._resources, self._session_agent_uid),
        )

    async def _dispatch_handler(
        self,
        handler: Callable[..., Awaitable[Any]],
        params: dict[str, Any],
    ) -> Any:
        """Shared call shape for the three per-item invocation handlers
        (tools/call fallback, resources/read, prompts/get) — each of
        gateway_handlers' handle_* functions takes the same context kwargs."""
        return await handler(
            params,
            resources=self._resources,
            supervisor=self._supervisor,
            prefs=self._prefs,
            ensure_subscribed=self._ensure_subscribed,
            on_evict=self._on_upstream_evicted,
            tool_reach=self._tool_reach,
            **self._log_ctx,
        )

    # --- Upstream → downstream notification forwarding ---

    async def _on_upstream_notification(self, server_name: str, notification: Any) -> None:
        await forward_upstream_notification(
            server_name,
            notification,
            discovery=self._discovery,
            send_downstream=self._send_downstream,
        )

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

        await self._degraded.dispose()
        await self._supervisor.dispose()
        self._notification_subscriptions.clear()
        # Let the composition root drop its registry entry last, after
        # the supervisor is fully disposed.
        if self._on_dispose is not None:
            with contextlib.suppress(Exception):
                self._on_dispose()
