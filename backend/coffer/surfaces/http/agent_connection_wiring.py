"""Wiring for an agent's Coffer connection (spec agent-registry "Connect an agent
to Coffer in one action").

The connection is the agent kind's, but one of its parts — the memory delivery
hook — is the memory kind's, and the two kinds may not import each other. This
module is where they meet: it adapts ``DeliveryService`` to the agent kind's
``ConnectionPart`` port and builds the one ``AgentConnectionService`` the
routes and the memory hook's reconcile pass both use.
"""

from __future__ import annotations

from coffer.application.agent.connection_service import (
    AgentConnectionService,
    McpConnectionPart,
    PartStatus,
)
from coffer.application.agent.mcp_service import AgentMcpService
from coffer.application.agent.service import AgentService
from coffer.application.memory.delivery import DeliveryService
from coffer.domain.agent.types import AgentType
from coffer.surfaces.http.agent_dependencies import set_agent_connection_service

#: The memory delivery hook's part key.
MEMORY_HOOK_PART = "memory_hook"


class MemoryHookConnectionPart:
    """The memory delivery hook, as a connection part."""

    key = MEMORY_HOOK_PART

    def __init__(self, delivery: DeliveryService) -> None:
        self._delivery = delivery

    def supports(self, agent_type: AgentType) -> bool:
        return self._delivery.supports(agent_type)

    async def status(self, agent_uid: str) -> PartStatus:
        st = await self._delivery.status(agent_uid)
        return PartStatus(
            key=self.key,
            installed=st.installed,
            detail=st.command if st.installed else None,
        )

    async def install(self, agent_uid: str, *, actor: str) -> None:
        await self._delivery.install(agent_uid, actor=actor)

    async def remove(self, agent_uid: str, *, actor: str) -> None:
        await self._delivery.remove(agent_uid, actor=actor)


def wire_agent_connection(
    agent_service: AgentService,
    mcp: AgentMcpService,
    delivery: DeliveryService,
) -> AgentConnectionService:
    """Build the connection service over its parts, the gateway entry first,
    and register it for the routes."""
    service = AgentConnectionService(
        agent_service=agent_service,
        parts=(McpConnectionPart(mcp), MemoryHookConnectionPart(delivery)),
    )
    set_agent_connection_service(service)
    return service
