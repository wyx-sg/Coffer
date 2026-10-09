"""MCPGatewaySession — per-downstream-client routing brain.

One instance per downstream MCP client connection; owns its SubprocessSupervisor
(per-upstream connections), shares a CapabilityDiscovery, and forwards upstream
notifications downstream. Invocation handlers live in `gateway_handlers`, the
tools/list composition in `gateway_tools_list`, sampling and roots in
`gateway_server_requests`, cancellable in-flight requests in `gateway_inflight`,
envelope parsing in `gateway_parsing` and the per-agent filter in `gateway_scope`.
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
)
from coffer.application.mcp.gateway_ask import dispatch_turn_ask, turn_is_live, with_ask_tool
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
from coffer.application.mcp.gateway_inflight import InflightRequests
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
    wire_connection,
)
from coffer.application.mcp.gateway_tool_gate import group_descriptions, hidden_tool_names
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
from coffer.application.mcp.upstream_auth import UpstreamAuthMonitor
from coffer.application.resource_service import ResourceService
from coffer.application.runtime.supervisor import spawn
from coffer.application.turn_ask import ASK_TOOL_NAME, TurnAskPort
from coffer.domain.errors import UpstreamUnavailable
from coffer.domain.mcp.jsonrpc_errors import INVALID_REQUEST, METHOD_NOT_FOUND, JsonRpcError

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
        auth_monitor: UpstreamAuthMonitor | None = None,
        turn_ask: TurnAskPort | None = None,
    ) -> None:
        self.id = session_id or str(uuid.uuid4())
        self._auth_monitor = auth_monitor
        self._resources = resource_service
        self._supervisor = supervisor
        self._discovery = discovery
        self._prefs = preferences
        self._invocations = invocations
        self._downstream_sink = downstream_sink
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        # The bound agent **uid** from ``initialize`` (params._meta["coffer/agent-uid"],
        # ADR identity-is-the-uid-inside-the-file); None sees only unscoped servers.
        self._session_agent_uid: str | None = None
        # Called once on dispose: the root drops this session's supervisor.
        self._on_dispose = on_dispose
        # ``is not None``, not ``or``: a registry with every tool off is falsy.
        self._registry = builtin_tools if builtin_tools is not None else BuiltinToolRegistry()
        # Tool tiering: how much of the catalogue this session lists (None = read env).
        self._tiering = tiering or load_tiering_config()
        # Upstream tools tiering left unlisted (estimated at initialize, real at tools/list).
        self.last_hidden_count = 0
        # The agent's launch cwd (params._meta["coffer/cwd"]), threaded into built-in calls.
        self._session_cwd: str | None = None
        # The turn's ``X-Coffer-Turn`` token (set per request); turn-scoped tools need it live.
        self._turn_ask = turn_ask
        self.turn_token: str | None = None
        # Servers whose notifications this session already subscribed to.
        self._notification_subscriptions: set[str] = set()
        # The loop holds tasks weakly; strong refs keep a notification from being collected.
        self._notification_tasks: set[asyncio.Task[None]] = set()
        # Servers whose discovery failed on the last tools/list; the tracker retries them.
        self._degraded = DegradedTracker(discovery, self._send_downstream)
        # Downstream client capabilities declared during initialize.
        self._client_capabilities: dict[str, Any] = {}
        # The MCP version agreed at ``initialize``; None until it succeeded. The
        # handshake happens once per session: identity, capabilities and cwd are
        # fixed for the session's life (spec mcp-gateway "Take the agent identity
        # from the handshake").
        self.protocol_version: str | None = None
        # Requests still being answered, by id, so the client can cancel one.
        self.inflight = InflightRequests()
        # Server-initiated request bookkeeping (sampling and roots).
        self._server_request_registry = ServerRequestRegistry()
        # SDK callbacks for sampling and roots, wired into every connection this
        # session's supervisor builds BEFORE it starts (``wire_connection``).
        self._callbacks = build_session_callbacks(
            self._server_request_registry,
            lambda: self._downstream_sink,
            lambda: self._client_capabilities,
            self.id,
        )
        if supervisor is not None:  # some unit tests build a session without one
            supervisor.prepare_connection = self._prepare_connection

    def set_downstream_sink(self, sink: NotificationSink) -> None:
        """Called by the session runner once the downstream wire is open."""
        self._downstream_sink = sink

    # --- Initialize ---

    async def handle_initialize(
        self,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Respond to the client's initialize request with coffer's server capabilities."""
        if self.protocol_version is not None:
            raise JsonRpcError(INVALID_REQUEST, "this session is already initialized")
        # The client's capabilities gate server-initiated requests (sampling).
        self._client_capabilities = params.get("capabilities", {}) or {}
        self._session_cwd = _extract_cwd(params)
        # The identity scope is evaluated against (params._meta["coffer/agent-uid"]).
        self._session_agent_uid = _extract_agent_uid(params)
        # The instructions field is the only channel into the client's system
        # prompt and is read before the first tools/list, so the unlisted count
        # comes from the saved tool lists; it names only the built-ins listed now.
        self.last_hidden_count = await saved_hidden_count(
            self._resources,
            self._session_agent_uid,
            prefs=self._prefs,
            invocations=self._invocations,
            config=self._tiering,
            clock=self._clock,
        )
        result = build_initialize_result(
            hidden_count=self.last_hidden_count,
            tools=[tool.name for tool in self._registry.list()],
            knowledge=self._registry.directory("knowledge") is not None,
        )
        self.protocol_version = result["protocolVersion"]
        return result

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
        raise JsonRpcError(METHOD_NOT_FOUND, f"method not found: {method!r}")

    def handle_response_from_downstream(self, envelope: dict[str, Any]) -> bool:
        """Route a JSON-RPC response to a pending server-initiated request; True if matched."""
        return self._server_request_registry.handle_response(envelope)

    @property
    def _log_ctx(self) -> dict[str, Any]:
        """What every path that records an invocation needs to write its row
        (the uid the session reported on ``initialize``, or ``None``)."""
        return {
            "invocations": self._invocations,
            "session_id": self.id,
            "session_agent_uid": self._session_agent_uid,
            "clock": self._clock,
        }

    async def _enabled_mcp_servers(self) -> list[str]:
        return await enabled_mcp_servers(self._resources, self._session_agent_uid)

    async def _servers_and_hidden(
        self,
    ) -> tuple[list[str], frozenset[str], dict[str, str], dict[str, str]]:
        """Visible server names, tools hidden from this agent, per-tool exposure
        overrides, and the custom-tool groups' descriptions."""
        rows = await visible_mcp_servers(self._resources, self._session_agent_uid)
        hidden = hidden_tool_names(rows)
        exposure = await exposure_overrides(self._prefs, rows)
        return [r.name for r in rows], hidden, exposure, group_descriptions(rows)

    async def _ensure_subscribed(self, server_name: str) -> None:
        """Make sure this session holds a connection to ``server_name``, whose
        handlers ``_prepare_connection`` wired in before it started."""
        if server_name in self._notification_subscriptions:
            return
        try:
            await self._supervisor.get_or_spawn(server_name)
        except UpstreamUnavailable:
            return
        self._notification_subscriptions.add(server_name)

    def _prepare_connection(self, server_name: str, conn: Any) -> None:
        """Wire this session's handlers into a connection before it starts."""

        def _notify(notif: Any) -> asyncio.Task[None]:
            coro = self._on_upstream_notification(server_name, notif)
            task = spawn(coro, name=f"mcp-upstream-notification:{server_name}")
            self._notification_tasks.add(task)
            task.add_done_callback(self._notification_tasks.discard)
            return task

        wire_connection(conn, _notify, self._client_capabilities, self._callbacks)

    @property
    def degraded_servers(self) -> set[str]:
        """Servers whose tools are missing from the last listing (tool tiering)."""
        return self._degraded.servers

    async def recover_degraded_now(self) -> bool:
        """Re-discover degraded servers once; True if any recovered."""
        return await self._degraded.recover_now()

    # --- tools/list, resources/list, prompts/list (fan-out: gateway_aggregate_lists.py) ---

    @property
    def _builtin(self) -> BuiltinToolRegistry:
        """The built-ins this session sees now: turn-scoped ones only inside a live turn."""
        return self._registry.view(in_turn=turn_is_live(self._turn_ask, self.turn_token))

    async def _handle_tools_list(self) -> dict[str, Any]:
        servers, hidden, exposure, _ = await self._servers_and_hidden()
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
        return {"tools": with_ask_tool(listing.tools, self._turn_ask, self.turn_token)}

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
            servers, hidden, exposure, about = await self._servers_and_hidden()
            return await run_tool_search(
                params,
                exposure=exposure,
                about=about,
                discovery=self._discovery,
                ensure_subscribed=self._ensure_subscribed,
                servers=servers,
                hidden=hidden,
                **self._log_ctx,
            )
        if name == ASK_TOOL_NAME:
            return await dispatch_turn_ask(
                params=params, port=self._turn_ask, token=self.turn_token, **self._log_ctx
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
            auth_monitor=self._auth_monitor,
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
        # Cancel any in-flight server-initiated requests and client requests
        self._server_request_registry.cancel_all()
        self.inflight.cancel_all()

        await self._degraded.dispose()
        await self._supervisor.dispose()
        self._notification_subscriptions.clear()
        # Let the composition root drop its registry entry last, after
        # the supervisor is fully disposed.
        if self._on_dispose is not None:
            with contextlib.suppress(Exception):
                self._on_dispose()
