"""FastAPI dependency providers for the one ``memory`` kind.

Same ``set_*`` / ``get_*`` singleton shape as ``surfaces.http.dependencies``,
typed concretely: the derived-tree service, the overrides table, and the
explicit-install delivery half.
"""

from __future__ import annotations

from coffer.application.memory.delivery import DeliveryService
from coffer.application.memory.service import MemoryService
from coffer.infrastructure.persistence.memory_overrides_repo import OverrideRepository

_memory_service: MemoryService | None = None


def set_memory_service(svc: MemoryService) -> None:
    """Called by the composition root once on startup."""
    global _memory_service
    _memory_service = svc


def get_memory_service() -> MemoryService:
    """FastAPI Depends() target."""
    if _memory_service is None:
        raise RuntimeError("memory service not initialised")
    return _memory_service


_memory_override_repo: OverrideRepository | None = None


def set_memory_override_repo(repo: OverrideRepository) -> None:
    """Called by the composition root once on startup."""
    global _memory_override_repo
    _memory_override_repo = repo


def get_memory_override_repo() -> OverrideRepository:
    """FastAPI Depends() target."""
    if _memory_override_repo is None:
        raise RuntimeError("memory override repo not initialised")
    return _memory_override_repo


_memory_delivery_service: DeliveryService | None = None


def set_memory_delivery_service(svc: DeliveryService) -> None:
    """Called by the composition root once on startup."""
    global _memory_delivery_service
    _memory_delivery_service = svc


def get_memory_delivery_service() -> DeliveryService:
    """FastAPI Depends() target."""
    if _memory_delivery_service is None:
        raise RuntimeError("memory delivery service not initialised")
    return _memory_delivery_service
