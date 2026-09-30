"""Wire the description of Coffer's own ``coffer`` MCP server.

The MCP kind describes the server (``surfaces.http.mcp.builtin_routes``); which
agents reach it is the agent kind's knowledge — an agent is connected exactly
when its MCP config holds Coffer's entry. The two kinds may not import each
other, so this composition module hands the MCP route a callable over the agent
kind's services.
"""

from __future__ import annotations

import contextlib

from coffer.application.agent.mcp_service import AgentMcpService
from coffer.application.agent.service import AgentService
from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.surfaces.http.mcp.builtin_routes import BuiltinServerSource, set_builtin_server_source


def wire_builtin_server(
    builtin_tools: BuiltinToolRegistry, agents: AgentService, connections: AgentMcpService
) -> None:
    async def connected_agents() -> list[str]:
        uids: list[str] = []
        for agent in await agents.list():
            # An agent whose type has no MCP config, or whose file does not
            # parse, is simply not listed as connected.
            with contextlib.suppress(Exception):
                if (await connections.status(agent.uid)).installed:
                    uids.append(agent.uid)
        return uids

    set_builtin_server_source(
        BuiltinServerSource(tools=builtin_tools, connected_agents=connected_agents)
    )


__all__ = ["wire_builtin_server"]
