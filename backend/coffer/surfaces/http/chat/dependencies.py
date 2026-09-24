"""FastAPI dependency providers for the turn platform (the ``chat`` kind).

Conversations, the agent-provider registry and the turn orchestrator were
first built for the web chat page and outlived it: IM channels are now their
only client. Same ``set_*`` / ``get_*`` singleton shape as
``surfaces.http.dependencies``, typed concretely.

``model_catalog`` is the one seam that crosses a kind: the models an agent can
be put on are the agent kind's knowledge (``AgentModelCatalogueService``), and
this kind consumes them through its own ``ModelCatalogPort`` — the composition
root publishes the agent service here, and the chat surface never imports the
agent kind.
"""

from __future__ import annotations

from coffer.application.chat.attachments import ChatAttachmentService
from coffer.application.chat.ports import ModelCatalogPort
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator

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


_attachment_service: ChatAttachmentService | None = None


def set_attachment_service(svc: ChatAttachmentService) -> None:
    """Called by the composition root once on startup."""
    global _attachment_service
    _attachment_service = svc


def get_attachment_service() -> ChatAttachmentService:
    """FastAPI Depends() target."""
    if _attachment_service is None:
        raise RuntimeError("chat attachment service not initialised")
    return _attachment_service
