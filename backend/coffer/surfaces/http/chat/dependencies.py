"""FastAPI dependency providers for the turn platform (the ``chat`` kind).

Conversations, the agent-provider registry and the turn orchestrator were
first built for the web chat page and outlived it: IM channels are now their
only client (the web lists their conversations and stops their turns). Same
``set_*`` / ``get_*`` singleton shape as
``surfaces.http.dependencies``, typed concretely.

``model_catalog`` is the one seam that crosses a kind: the models an agent can
be put on are the agent kind's knowledge (``AgentModelCatalogueService``), and
this kind consumes them through its own ``ModelCatalogPort`` — the composition
root publishes the agent service here, and the chat surface never imports the
agent kind.
"""

from __future__ import annotations

from coffer.application.chat.ports import ChannelPlacesPort, ModelCatalogPort
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator
from coffer.infrastructure.chat.adapter_support import ChannelNoteResolver

_chat_service: ChatService | None = None


def set_chat_service(svc: ChatService) -> None:
    """Called by the composition root once on startup."""
    global _chat_service
    _chat_service = svc


def get_chat_service() -> ChatService:
    """FastAPI Depends() target."""
    if _chat_service is None:
        raise RuntimeError("chat service not initialised")
    return _chat_service


_turn_orchestrator: TurnOrchestrator | None = None


def set_turn_orchestrator(orchestrator: TurnOrchestrator) -> None:
    """Called by the composition root once on startup."""
    global _turn_orchestrator
    _turn_orchestrator = orchestrator


def get_turn_orchestrator() -> TurnOrchestrator:
    """FastAPI Depends() target."""
    if _turn_orchestrator is None:
        raise RuntimeError("turn orchestrator not initialised")
    return _turn_orchestrator


_agent_registry: AgentProviderRegistry | None = None


def set_agent_registry(registry: AgentProviderRegistry) -> None:
    """Called by the composition root once on startup."""
    global _agent_registry
    _agent_registry = registry


def get_agent_registry() -> AgentProviderRegistry:
    """FastAPI Depends() target."""
    if _agent_registry is None:
        raise RuntimeError("agent registry not initialised")
    return _agent_registry


_model_catalog: ModelCatalogPort | None = None


def set_model_catalog(catalog: ModelCatalogPort) -> None:
    """Called by the composition root once on startup, with the agent kind's
    catalogue service — it satisfies the port structurally."""
    global _model_catalog
    _model_catalog = catalog


def get_model_catalog() -> ModelCatalogPort:
    """FastAPI Depends() target."""
    if _model_catalog is None:
        raise RuntimeError("model catalog not initialised")
    return _model_catalog


_channel_places: ChannelPlacesPort | None = None
_channel_note_reader: ChannelNoteResolver | None = None


def set_channel_note_reader(reader: ChannelNoteResolver | None) -> None:
    """Called by the channel kind's composition (spec channels "Tell a
    channel-driven agent it is on a chat channel"); ``None`` unwires it."""
    global _channel_note_reader
    _channel_note_reader = reader


def get_channel_note_reader() -> ChannelNoteResolver | None:
    """The channel kind's note reader, or ``None`` when no channel kind is wired
    — the note then names the channel only."""
    return _channel_note_reader


def set_channel_places(places: ChannelPlacesPort | None) -> None:
    """Called by the channel kind's composition (spec chat
    "Show channel conversations on the Conversations page"); ``None`` unwires it."""
    global _channel_places
    _channel_places = places


def get_channel_places() -> ChannelPlacesPort | None:
    """FastAPI Depends() target. ``None`` when no channel kind is wired — the
    list then shows no place."""
    return _channel_places
