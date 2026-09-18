"""What a downstream client sees when it lists tools.

Three steps, and each can be wrong on its own, which is why they are named
here rather than inlined in the session: the upstreams are aggregated, Coffer's
own built-ins are appended, and tiering hides the tail of a list too long to be
useful (ADR budget-driven-tool-tiering).

Extracted from ``gateway`` to keep the session class within its file-size
budget, alongside ``gateway_aggregate_lists`` (the fan-out), ``gateway_tiering``
(the policy) and ``gateway_handlers`` (the invocations). This module is the
composition of the first two plus the built-ins; it holds no policy of its own.

The failed servers are recorded on the degraded tracker rather than swallowed:
a client that cached a truncated list would never see those tools again this
session, so the tracker re-discovers them and tells the client to re-list. They
are still on the returned listing, because that is what the recording is made
of and a caller reading one should be able to see the other.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.mcp.gateway_aggregate_lists import list_tools_across
from coffer.application.mcp.gateway_builtin import append_builtin_tools
from coffer.application.mcp.gateway_recovery import DegradedTracker
from coffer.application.mcp.gateway_tiering import apply_tiering
from coffer.application.mcp.ports import MCPInvocationRepoPort
from coffer.application.mcp.tiering_config import TieringConfig


class ToolsListing:
    """The listing, and the two facts the session has to record about it."""

    __slots__ = ("failed_servers", "hidden_count", "tools")

    def __init__(
        self, tools: list[dict[str, Any]], hidden_count: int, failed_servers: list[str]
    ) -> None:
        self.tools = tools
        self.hidden_count = hidden_count
        self.failed_servers = failed_servers


async def build_tools_listing(
    *,
    discovery: CapabilityDiscovery,
    ensure_subscribed: Callable[[str], Awaitable[None]],
    servers: list[str],
    builtin: BuiltinToolRegistry,
    invocations: MCPInvocationRepoPort,
    tiering: TieringConfig,
    clock: Callable[[], datetime],
    degraded: DegradedTracker,
) -> ToolsListing:
    """Aggregate, append the built-ins, then hide what tiering says to hide."""
    outcome = await list_tools_across(discovery, ensure_subscribed, servers)
    tools = list(outcome.items)
    append_builtin_tools(tools, builtin)
    tiered = await apply_tiering(tools, invocations=invocations, config=tiering, clock=clock)
    degraded.record(outcome.failed_servers)
    return ToolsListing(tiered.listed, tiered.hidden_count, outcome.failed_servers)
