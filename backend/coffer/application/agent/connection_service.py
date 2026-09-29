"""AgentConnectionService — connect an agent to Coffer, or disconnect it, in one act.

Spec agent-registry "Connect an agent to Coffer in one action", "Report an
agent's Coffer connection part by part" and "Disconnect an agent from Coffer".

Connecting installs every *part* Coffer writes into the agent's own
configuration that applies to it right now; disconnecting takes every one of
them out again. A part is one marker-scoped entry with its own install,
removal, audit event and status, owned by the kind that knows how to write it:

- ``mcp`` — the gateway entry (``coffer`` in the agent's MCP config),
  written by :class:`~coffer.application.agent.mcp_service.AgentMcpService`.
  It applies to every agent type, and it is the *anchor*: an agent carrying it
  is the one Coffer treats as connected when something later has to decide
  where a newly applicable part goes (the ``memory`` switch turned on).
- ``memory_hook`` — the memory delivery hook, which the memory kind owns. The
  agent kind cannot import the memory kind, so the composition root adapts it
  to :class:`ConnectionPart` and hands it in; it applies only while the
  ``memory`` experimental feature is on.

This service owns no write of its own: each part keeps its own atomic write,
``.bak`` and audit event, so a connect is recorded as the part installs it
performed, exactly as each was recorded when it was its own button.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from coffer.application.agent.mcp_service import AgentMcpService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.descriptor import descriptor_for
from coffer.domain.agent.types import AgentType
from coffer.domain.resource import Resource

#: The key of the anchor part (see the module docstring).
MCP_PART = "mcp"


class ConnectionState(StrEnum):
    """How much of what applies to an agent is in place."""

    #: Every applicable part is installed.
    CONNECTED = "connected"
    #: Some applicable parts are installed and some are not — connecting again
    #: puts the rest in place.
    PARTIAL = "partial"
    #: No applicable part is installed.
    DISCONNECTED = "disconnected"


@dataclass(frozen=True)
class PartStatus:
    """One part, as the agent's own configuration has it right now."""

    key: str
    installed: bool
    #: What is installed, when it is (the shim command, the hook command);
    #: otherwise whatever the part can say about what it would write, or None.
    detail: str | None


@dataclass(frozen=True)
class ConnectionStatus:
    state: ConnectionState
    #: The parts that apply to this agent now, in install order.
    parts: tuple[PartStatus, ...]


class ConnectionPart(Protocol):
    """One thing Coffer writes into an agent to connect it."""

    @property
    def key(self) -> str: ...

    def supports(self, agent_type: AgentType) -> bool:
        """Whether this part exists for the type at all. A part that does is
        removed on disconnect whether or not it currently applies."""
        ...

    def enabled(self) -> bool:
        """Whether the part applies right now (its feature is switched on)."""
        ...

    async def status(self, agent_uid: str) -> PartStatus: ...

    async def install(self, agent_uid: str, *, actor: str) -> None:
        """Install or refresh the part. Idempotent; audited by the part."""
        ...

    async def remove(self, agent_uid: str, *, actor: str) -> None:
        """Take out only Coffer's entry. A no-op, writing and auditing
        nothing, when it is not there."""
        ...


class McpConnectionPart:
    """The gateway entry, as a connection part."""

    key = MCP_PART

    def __init__(self, mcp: AgentMcpService) -> None:
        self._mcp = mcp

    def supports(self, agent_type: AgentType) -> bool:
        return descriptor_for(agent_type).mcp is not None

    def enabled(self) -> bool:
        return True

    async def status(self, agent_uid: str) -> PartStatus:
        st = await self._mcp.status(agent_uid)
        return PartStatus(key=self.key, installed=st.installed, detail=st.command)

    async def install(self, agent_uid: str, *, actor: str) -> None:
        await self._mcp.install(agent_uid, actor=actor)

    async def remove(self, agent_uid: str, *, actor: str) -> None:
        await self._mcp.uninstall(agent_uid, actor=actor)


class _AgentLookup(Protocol):
    async def get(self, uid: str, /) -> Resource: ...
    async def list(self) -> list[Resource]: ...


def _state(parts: Sequence[PartStatus]) -> ConnectionState:
    installed = sum(1 for p in parts if p.installed)
    if parts and installed == len(parts):
        return ConnectionState.CONNECTED
    if installed == 0:
        return ConnectionState.DISCONNECTED
    return ConnectionState.PARTIAL


class AgentConnectionService:
    def __init__(self, *, agent_service: _AgentLookup, parts: Sequence[ConnectionPart]) -> None:
        if not parts or parts[0].key != MCP_PART:
            raise ValueError("the gateway entry must be the first connection part")
        self._agents = agent_service
        self._parts = tuple(parts)

    async def _type(self, agent_uid: str) -> AgentType:
        """The agent's type. Raises ResourceNotFound (→ 404) for an unknown uid."""
        resource = await self._agents.get(agent_uid)
        return AgentConfig.model_validate(resource.config).type

    def _applicable(self, agent_type: AgentType) -> tuple[ConnectionPart, ...]:
        return tuple(p for p in self._parts if p.supports(agent_type) and p.enabled())

    async def status(self, agent_uid: str) -> ConnectionStatus:
        """Read from the agent's own files, never stored; writes nothing."""
        agent_type = await self._type(agent_uid)
        parts = tuple([await p.status(agent_uid) for p in self._applicable(agent_type)])
        return ConnectionStatus(state=_state(parts), parts=parts)

    async def connect(self, agent_uid: str, *, actor: str) -> ConnectionStatus:
        """Install every applicable part, in order, the gateway entry first.

        Every part is (re)installed rather than only the missing ones: an
        install is also how a stale entry — a shim path an upgrade moved, a
        hook command an older build wrote — is brought up to date. The gateway
        entry goes first because its refusal (no shim to point at) writes
        nothing, so a connect that cannot work fails before touching anything.
        """
        agent_type = await self._type(agent_uid)
        for part in self._applicable(agent_type):
            await part.install(agent_uid, actor=actor)
        return await self.status(agent_uid)

    async def disconnect(self, agent_uid: str, *, actor: str) -> ConnectionStatus:
        """Remove every part the type has, applicable now or not — a part whose
        feature is off may still have been left behind — each taking out only
        Coffer's own entry."""
        agent_type = await self._type(agent_uid)
        for part in self._parts:
            if part.supports(agent_type):
                await part.remove(agent_uid, actor=actor)
        return await self.status(agent_uid)

    async def connected_agents(self) -> list[str]:
        """The uids of every agent carrying the gateway entry.

        What a part that has just started to apply is installed into: an
        agent the user connected is one that should have it, and an agent they
        never connected (or disconnected) is not given anything. Best-effort
        per agent: an unreadable config file leaves that agent out rather than
        failing the rest.
        """
        anchor = self._parts[0]
        out: list[str] = []
        for resource in await self._agents.list():
            try:
                if (await anchor.status(resource.uid)).installed:
                    out.append(resource.uid)
            except Exception:
                continue
        return out


__all__ = [
    "MCP_PART",
    "AgentConnectionService",
    "ConnectionPart",
    "ConnectionState",
    "ConnectionStatus",
    "McpConnectionPart",
    "PartStatus",
]
