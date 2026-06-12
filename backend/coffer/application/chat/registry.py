"""AgentProviderRegistry — the chat platform's agent-provider seam.

The chat surface, the turn orchestrator, and persistence reach an agent only
through this registry, keyed by the conversation's ``agent_key``. Adding another
agent to the platform is a single ``register`` call in the composition root — no
change to the chat surface, the persistence layer, or the wire contract.
"""

from __future__ import annotations

from dataclasses import dataclass

from coffer.application.chat.ports import AgentProvider
from coffer.domain.errors import UnknownAgent


@dataclass(frozen=True)
class RegisteredAgent:
    """A provider together with the display name shown in the agent picker."""

    provider: AgentProvider
    display_name: str


class AgentProviderRegistry:
    """Maps ``agent_key`` to its ``AgentProvider`` and display name."""

    def __init__(self) -> None:
        self._entries: dict[str, RegisteredAgent] = {}

    def register(self, provider: AgentProvider, *, display_name: str) -> None:
        """Register an agent provider under its ``agent_key``."""
        self._entries[provider.agent_key] = RegisteredAgent(
            provider=provider, display_name=display_name
        )

    def get(self, agent_key: str) -> AgentProvider:
        """Return the provider for ``agent_key``; raises ``UnknownAgent`` if none."""
        entry = self._entries.get(agent_key)
        if entry is None:
            raise UnknownAgent(agent_key)
        return entry.provider

    def entries(self) -> list[RegisteredAgent]:
        """Return every registered agent, in registration order."""
        return list(self._entries.values())
