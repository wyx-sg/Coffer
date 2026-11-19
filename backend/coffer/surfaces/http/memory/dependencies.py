"""FastAPI dependency providers for memory, set once by the composition root
(``memory_wiring``)."""

from __future__ import annotations

from coffer.application.memory.service import MemoryService
from coffer.application.memory.tidy import MemoryTidy

_service: MemoryService | None = None
_tidy: MemoryTidy | None = None


def set_memory_services(service: MemoryService, tidy: MemoryTidy) -> None:
    global _service, _tidy
    _service, _tidy = service, tidy


def get_memory_service() -> MemoryService:
    if _service is None:
        raise RuntimeError("memory service not initialised")
    return _service


def get_memory_tidy() -> MemoryTidy:
    if _tidy is None:
        raise RuntimeError("memory tidy not initialised")
    return _tidy
