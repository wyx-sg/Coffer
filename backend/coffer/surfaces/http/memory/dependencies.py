"""FastAPI dependency providers for the one ``memory`` kind.

Same ``set_*`` / ``get_*`` singleton shape as ``surfaces.http.dependencies``,
typed concretely: the derived-tree service, the hook service that answers
every delivery fire, and the delivery-stats service.
"""

from __future__ import annotations

from coffer.application.memory.delivery_stats import DeliveryStatsService
from coffer.application.memory.hook_service import MemoryHookService
from coffer.application.memory.service import MemoryService

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


_memory_hook_service: MemoryHookService | None = None
_memory_stats_service: DeliveryStatsService | None = None


def set_memory_hook_service(svc: MemoryHookService) -> None:
    """Called by the composition root once on startup."""
    global _memory_hook_service
    _memory_hook_service = svc


def set_memory_stats_service(svc: DeliveryStatsService) -> None:
    """Called by the composition root once on startup."""
    global _memory_stats_service
    _memory_stats_service = svc


def get_memory_hook_service() -> MemoryHookService:
    if _memory_hook_service is None:
        raise RuntimeError("memory hook service not initialised")
    return _memory_hook_service


def get_memory_stats_service() -> DeliveryStatsService:
    if _memory_stats_service is None:
        raise RuntimeError("memory delivery stats service not initialised")
    return _memory_stats_service
