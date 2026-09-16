"""Ports for the agent-chat platform (spec channels).

These Protocols are the **platform seam**: the chat surface, the turn
orchestrator, and persistence reach an agent only through them. Adding another
agent to the platform is a new ``AgentProvider`` registered at the composition
root — no change to the chat surface, persistence, or the wire contract.

Concrete implementations live in ``coffer.infrastructure.chat`` (the built-in
agent) and in tests (fakes).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any, Protocol

from coffer.domain.chat.attachment import Attachment
from coffer.domain.chat.events import AgentEvent
from coffer.domain.chat.message import Message


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
        attachments: Sequence[Attachment] = (),
    ) -> AsyncIterator[AgentEvent]:
        """Run one turn and yield its events.

        ``attachments`` are files supplied with this turn (channel media). An
        adapter materialises them in its own native shape — a vision agent inlines
        image/document content blocks; a path-native agent uses the paths. An
        adapter that ignores them still satisfies the seam (default empty)."""
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


class CatalogueModel(Protocol):
    """One model an agent can be put on, as the agent itself reports it.

    Structural mirror of the agent kind's ``AgentModel`` — the chat surface
    reads these five fields and nothing else."""

    @property
    def id(self) -> str: ...

    @property
    def label(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def efforts(self) -> Sequence[str]: ...

    @property
    def default_effort(self) -> str | None: ...


class ModelCatalogPort(Protocol):
    """What a model picker should OFFER for each registered agent.

    Answered by the agent kind (its catalogue service reads the agent's own
    executable, RPC and config, and narrows by the active connection), consumed
    by the turn platform's ``/agent-providers/{agent_key}/models`` route.
    Declared here so the chat kind never imports the agent kind: the
    composition root hands the agent service in, and it satisfies this port
    structurally.

    ``offered``, not ``catalogue``: the catalogue is what the agent can run on
    its OWN login, and an active connection means the turns do not go there.
    The web picker used to read the catalogue and merge the endpoint's models
    into it in the browser, so it offered ids that endpoint would reject, while
    a channel's ``/model`` card — which has always read ``offered`` in-process
    — offered the curated ones. One question, one answer, both surfaces.
    """

    async def offered(self, agent_key: str) -> Sequence[CatalogueModel]: ...
