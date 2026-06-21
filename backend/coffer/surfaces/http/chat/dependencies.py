"""Agent-chat (spec 008) FastAPI dependency providers.

Extracted from the kind-agnostic ``surfaces.http.dependencies`` to keep that
core module under its file-size budget. Re-exported from there so the long-
standing ``surfaces.http.dependencies.get_chat_service`` import paths still work.

Typed as ``Any`` to avoid importing chat-specific modules from kind-agnostic
core (Contract 6); concrete types are enforced at the chat route call sites.
"""

from __future__ import annotations

from typing import Any

_chat_service: Any | None = None


def set_chat_service(svc: Any) -> None:
    global _chat_service
    _chat_service = svc


def get_chat_service() -> Any:
    if _chat_service is None:
        raise RuntimeError("chat service not initialised")
    return _chat_service


_introspection_service: Any | None = None


def set_introspection_service(svc: Any) -> None:
    global _introspection_service
    _introspection_service = svc


def get_introspection_service() -> Any:
    if _introspection_service is None:
        raise RuntimeError("introspection service not initialised")
    return _introspection_service


_turn_orchestrator: Any | None = None


def set_turn_orchestrator(orchestrator: Any) -> None:
    global _turn_orchestrator
    _turn_orchestrator = orchestrator


def get_turn_orchestrator() -> Any:
    if _turn_orchestrator is None:
        raise RuntimeError("turn orchestrator not initialised")
    return _turn_orchestrator


_agent_registry: Any | None = None


def set_agent_registry(registry: Any) -> None:
    global _agent_registry
    _agent_registry = registry


def get_agent_registry() -> Any:
    if _agent_registry is None:
        raise RuntimeError("agent registry not initialised")
    return _agent_registry
