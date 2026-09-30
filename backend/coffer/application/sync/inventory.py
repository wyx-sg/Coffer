"""Each agent on this machine and the plugins it has, for this machine's
descriptor (spec vault-sync "Record plugins as an inventory, not a replicator").

An inventory, not a replicator: the list is written down so a person on a new
machine knows what to install with the vendor's own CLI. Nothing on any
machine writes an agent's plugin configuration from it — hand-writing another
tool's private config format corrupts it silently when the format moves (spec
agent-registry "Toggle a plugin through the documented location only").
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Protocol

from coffer.domain.resource import Resource
from coffer.domain.sync.machine import AgentInventory, Plugin

_log = logging.getLogger(__name__)


class _Agents(Protocol):
    async def list(self, *, kind: str) -> list[Resource]: ...


class _Plugins(Protocol):
    async def list_plugins(self, uid: str) -> Any: ...


class AgentPluginInventory:
    """Implements ``service_ports.AgentInventoryPort`` over the agent kind's
    rows and the agent plugin service's read half. The plugin service is
    looked up at each call: it is wired with the agent kind, after sync."""

    def __init__(self, agents: _Agents, plugins: Callable[[], _Plugins | None]) -> None:
        self._agents = agents
        self._plugins = plugins

    async def inventory(self) -> list[AgentInventory]:
        """One entry per agent. A read failure on one agent (an unreadable
        config dir, a config that no longer parses) lists it without plugins
        rather than failing the descriptor."""
        out: list[AgentInventory] = []
        lister = self._plugins()
        for resource in await self._agents.list(kind="agent"):
            agent_type = str(resource.config.get("type") or resource.name)
            plugins: tuple[Plugin, ...] = ()
            if lister is not None:
                try:
                    listing = await lister.list_plugins(resource.uid)
                except Exception:
                    _log.debug("sync.inventory.unreadable", extra={"agent": resource.name})
                else:
                    plugins = tuple(
                        sorted(
                            (
                                Plugin(
                                    id=str(p.id),
                                    name=str(getattr(p, "name", "") or ""),
                                    marketplace=getattr(p, "marketplace", None),
                                    enabled=bool(getattr(p, "enabled", True)),
                                    version=getattr(p, "version", None),
                                )
                                for p in getattr(listing, "items", [])
                            ),
                            key=lambda p: p.id,
                        )
                    )
            out.append(AgentInventory(type=agent_type, name=resource.name, plugins=plugins))
        return out


__all__ = ["AgentPluginInventory"]
