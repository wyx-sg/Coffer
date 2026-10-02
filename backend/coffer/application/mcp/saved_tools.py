"""The tool lists discovery last saved, read without connecting to anything.

Two readers want a server's tools without spawning it: the MCP server page's
tiering split, and the gateway's ``initialize``, whose instructions tell the
agent how many tools tiering leaves unlisted. Listing happens only after
``initialize``, so the count for the handshake has to come from what discovery
saved last (spec mcp-gateway "Forward tools, resources and prompts").
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from coffer.application.mcp.custom_tool_ports import ToolReachRepoPort
from coffer.application.mcp.gateway_scope import visible_mcp_servers
from coffer.application.mcp.gateway_tiering import apply_tiering
from coffer.application.mcp.gateway_tool_gate import hidden_tool_names
from coffer.application.mcp.ports import MCPCapabilityPreferenceRepoPort, MCPInvocationRepoPort
from coffer.application.mcp.tiering_config import TieringConfig
from coffer.application.mcp.tool_exposure import exposure_overrides
from coffer.application.resource_service import ResourceService
from coffer.domain.resource import Resource

_NEVER_SEEN = datetime.fromtimestamp(0, tz=UTC)


async def current_tools(
    prefs: MCPCapabilityPreferenceRepoPort, resource: Resource
) -> list[tuple[str, bool]]:
    """The tools discovery last saw for ``resource``, with their switch.

    Every rediscovery stamps each tool it still sees with one ``last_seen_at``;
    rows for tools the server no longer offers keep an older stamp, so the
    current set is the rows carrying the newest one. A tool switched off on
    another machine and never seen here has no stamp, and is not current.
    """
    rows = [r for r in await prefs.list_for(resource.uid, "tool") if r.last_seen_at > _NEVER_SEEN]
    if not rows:
        return []
    newest = max(r.last_seen_at for r in rows)
    return [(r.capability_key, r.enabled) for r in rows if r.last_seen_at == newest]


async def saved_hidden_count(
    resources: ResourceService,
    agent_uid: str | None,
    tool_reach: ToolReachRepoPort | None,
    *,
    prefs: MCPCapabilityPreferenceRepoPort,
    invocations: MCPInvocationRepoPort,
    config: TieringConfig,
    clock: Callable[[], datetime],
) -> int:
    """How many upstream tools tiering leaves unlisted for the session of
    ``agent_uid``, from the saved lists of the servers it can see (minus the
    tools its reach hides).

    Never raises: a handshake must not fail over a statistics problem, and
    zero is what an agent is told when nothing is known to be unlisted.
    """
    try:
        rows = await visible_mcp_servers(resources, agent_uid)
        hidden = await hidden_tool_names(rows, agent_uid, tool_reach)
        tools = [
            {"name": f"{server.name}__{name}"}
            for server in rows
            for name, enabled in await current_tools(prefs, server)
            if enabled and f"{server.name}__{name}" not in hidden
        ]
        result = await apply_tiering(
            tools,
            invocations=invocations,
            config=config,
            clock=clock,
            exposure=await exposure_overrides(prefs, rows),
        )
    except Exception:
        return 0
    return result.hidden_count
