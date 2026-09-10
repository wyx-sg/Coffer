"""Composition-root singletons for the turn platform.

The turn platform — conversations, the agent-provider registry, the turn
orchestrator, the model catalogue — was first built for the web chat page and
outlived it: IM channels (spec channels) are now its only client, and the provider
editors reuse the introspection service. These accessors were extracted from
the kind-agnostic ``surfaces.http.dependencies`` to keep that module under its
file-size budget, and are re-exported from there so the long-standing import
paths still work.

Typed as ``Any`` so kind-agnostic core need not import turn-specific modules
(Contract 6); concrete types are enforced at the route call sites.
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


_agent_model_catalogue: Any | None = None


def set_agent_model_catalogue(svc: Any) -> None:
    global _agent_model_catalogue
    _agent_model_catalogue = svc


def get_agent_model_catalogue() -> Any:
    if _agent_model_catalogue is None:
        raise RuntimeError("agent model catalogue not initialised")
    return _agent_model_catalogue
