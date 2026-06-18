"""Ports for the agent-chat platform (spec 008).

These Protocols are the **platform seam**: the chat surface, the turn
orchestrator, and persistence reach an agent only through them. Adding another
agent to the platform is a new ``AgentProvider`` registered at the composition
root — no change to the chat surface, persistence, or the wire contract.

Concrete implementations live in ``coffer.infrastructure.chat`` (the built-in
agent) and in tests (fakes).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from coffer.domain.chat.events import AgentEvent
from coffer.domain.chat.message import Message


@dataclass(frozen=True)
class ToolSpec:
    """Describes a single tool exposed by the MCP gateway.

    Not part of the frozen platform seam — ``ToolGateway`` / ``ToolSpec`` are an
    infrastructure-side collaborator of the built-in agent, injected into its
    adapter at build time. Other agents need not use them.
    """

    name: str
    description: str
    input_schema: dict[str, Any]


class ToolGateway(Protocol):
    """The built-in agent's view of Coffer's aggregated tool surface."""

    async def list_tools(self) -> list[ToolSpec]: ...

    async def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]: ...


class AgentAdapter(Protocol):
    """One agent's handling of one turn.

    The adapter is **self-contained**: it carries its own model, tools, and
    configuration, injected by its ``AgentProvider`` when the adapter is built.
    ``run_turn`` is given only the conversation history and yields a stream of
    ``AgentEvent``s.

    It MUST yield a terminal ``TurnDone`` or ``TurnError`` before the iterator
    ends (unless cancelled), and on ``asyncio.CancelledError`` it MUST clean up
    and re-raise.

    An adapter MAY additionally expose a ``model_id: str`` attribute naming the
    model the turn ran on; the orchestrator records it on the assistant message
    when present. It is optional — adapters that bring no Coffer-registered
    model simply omit it — so it is not part of this frozen Protocol.
    """

    async def run_turn(
        self,
        *,
        history: Sequence[Message],
    ) -> AsyncIterator[AgentEvent]:
        """Run one turn and yield its events."""
        ...


class AgentProvider(Protocol):
    """The platform's unit of extension: one provider owns one agent type.

    Providers are held in the ``AgentProviderRegistry``. The chat surface knows
    only the registry — never a specific provider — so a second agent is a new
    registry entry, not a re-architecture.
    """

    agent_key: str

    async def init_conversation(self, conversation_id: str, agent_config: dict[str, Any]) -> None:
        """Validate and persist agent-specific config when a conversation is
        created. An invalid config raises a domain error (mapped to 400)."""
        ...

    async def build_adapter(self, conversation_id: str) -> AgentAdapter:
        """Build a configured ``AgentAdapter`` for one turn of the conversation."""
        ...

    async def on_conversation_deleted(self, conversation_id: str) -> None:
        """Tear down agent-specific state for a deleted conversation; idempotent."""
        ...

    async def availability(self) -> bool:
        """Whether this agent can currently be picked for a new conversation."""
        ...
