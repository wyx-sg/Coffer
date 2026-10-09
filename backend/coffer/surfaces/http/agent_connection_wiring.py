"""Wiring for an agent's Coffer connection (spec agent-registry "Connect an agent
to Coffer in one action").

Builds the one ``AgentConnectionService`` the routes use, over its one part:
the gateway entry.
"""

from __future__ import annotations

from coffer.application.agent.connection_service import (
    AgentConnectionService,
    McpConnectionPart,
)
from coffer.application.agent.mcp_service import AgentMcpService
from coffer.application.agent.service import AgentService
from coffer.surfaces.http.agent_dependencies import set_agent_connection_service


def wire_agent_connection(
    agent_service: AgentService, mcp: AgentMcpService
) -> AgentConnectionService:
    """Build the connection service over its parts and register it for the
    routes."""
    service = AgentConnectionService(agent_service=agent_service, parts=(McpConnectionPart(mcp),))
    set_agent_connection_service(service)
    return service
