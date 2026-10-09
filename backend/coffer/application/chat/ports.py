"""Ports for the agent-chat platform (spec chat).

These Protocols are the **platform seam**: the chat surface, the turn
orchestrator, and persistence reach an agent only through them. Adding another
agent to the platform is a new ``AgentProvider`` registered at the composition
root — no change to the chat surface, persistence, or the wire contract.

Concrete implementations live in ``coffer.infrastructure.chat`` (the Claude
Code and Codex providers) and in tests (fakes).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any, Protocol, TypeVar

from coffer.domain.chat.attachment import Attachment
from coffer.domain.chat.channel_place import ChannelPlaceView
from coffer.domain.chat.events import AgentEvent


class AgentAdapter(Protocol):
    """One agent's handling of one turn.

    The adapter is **self-contained**: it carries its own model, tools, and
    configuration, injected by its ``AgentProvider`` when the adapter is built.
    ``run_turn`` is given the turn's prompt and attachments — the agent's own
    session (resumed by the adapter) holds the conversation — and yields a
    stream of ``AgentEvent``s.

    It MUST yield a terminal ``TurnDone`` or ``TurnError`` before the iterator
    ends (unless cancelled), and on ``asyncio.CancelledError`` it MUST clean up
    and re-raise.

    An adapter MAY additionally expose a ``model_id: str`` attribute naming the
    model the turn ran on. It is optional, so it is not part of this frozen
    Protocol.
    """

    async def run_turn(
        self,
        prompt: str,
        attachments: Sequence[Attachment] = (),
    ) -> AsyncIterator[AgentEvent]:
        """Run one turn and yield its events.

        ``prompt`` is the text the person sent. ``attachments`` are files supplied
        with this turn (channel media). An adapter materialises them in its own
        native shape — a vision agent inlines image/document content blocks; a
        path-native agent uses the paths. An adapter that ignores them still
        satisfies the seam (default empty)."""
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


_DepsT = TypeVar("_DepsT", contravariant=True)


class AgentDriver(Protocol[_DepsT]):
    """The driver facet of an agent (ADR agent-mechanisms-are-optional-facets-
    on-the-descriptor): how Coffer runs a turn on it.

    Bound to the agent's descriptor at the composition root — the driver says
    which agent it serves by ``agent_key`` (the agent type's value) — and asked
    by the chat composition to ``build`` the ``AgentProvider`` once the chat
    kind's own dependencies (``_DepsT``) exist. Drivers are direct: the Claude
    Agent SDK for Claude Code, ``codex app-server`` for Codex.
    """

    @property
    def agent_key(self) -> str: ...

    @property
    def display_name(self) -> str:
        """The name the agent picker shows."""
        ...

    def build(self, deps: _DepsT) -> AgentProvider: ...


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

    async def builtin_offered(self, agent_key: str) -> Sequence[CatalogueModel]:
        """The agent's own login's models, even while a connection is active."""
        ...

    async def native_default_model(self, agent_key: str) -> str | None: ...

    async def builtin_default(self, agent_key: str) -> CatalogueModel | None:
        """The model the agent's own login runs when its config names none, when
        the agent itself reports it; ``None`` otherwise."""
        ...

    async def resolved_default(self, agent_key: str) -> str | None:
        """The model a turn with no override runs on, when Coffer can know it."""
        ...


class ChannelPlacesPort(Protocol):
    """Where in its channel each conversation of a listing lives (spec chat
    "Show every agent's sessions on the Conversations page").

    Declared here, by the kind that consumes it; the channel kind satisfies it
    and the composition root wires the two, so chat never imports channel code.
    Absent (``None``) when no channel kind is wired — the list then shows no
    place."""

    async def places(self, conversation_ids: Sequence[str]) -> Mapping[str, ChannelPlaceView]:
        """Where in its channel each of ``conversation_ids`` lives, for the ones
        a channel opened; the others are absent. A constant number of reads
        whatever the number of ids — the listing calls it once per page."""
        ...


class ConversationSessionsPort(Protocol):
    """A conversation's native session, renamed and deleted through its agent
    (spec chat "Rename and delete a conversation through its agent").

    Declared here, by the kind that consumes it; the composition root satisfies
    it with the agent kind's sessions service, so chat never imports the agent
    kind. Both operations act on the agent's own record only: the caller owns
    the index row. A session the agent no longer has, or an agent that is not
    registered, is a no-op (there is nothing to change on the agent's side); an
    agent that refuses raises its own error, which the caller lets through.
    """

    async def rename(self, agent_key: str, session_id: str, title: str) -> None: ...

    async def delete(self, agent_key: str, session_id: str) -> None: ...


class SessionInUsePort(Protocol):
    """Whether a native session is being continued somewhere else (spec chat
    "Run a session in one place at a time")."""

    async def in_use(self, session_id: str) -> bool:
        """True when a process outside the daemon's own process tree has
        ``session_id`` among its arguments."""
        ...
