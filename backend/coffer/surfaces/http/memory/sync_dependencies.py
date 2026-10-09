"""FastAPI dependency providers for the memory sync, set once by the
composition root (``memory_sync_wiring``)."""

from __future__ import annotations

from coffer.application.memory.sync_service import MemorySyncService
from coffer.application.memory.sync_view import MemorySyncView

_service: MemorySyncService | None = None
_view: MemorySyncView | None = None


def set_sync_services(service: MemorySyncService, view: MemorySyncView) -> None:
    global _service, _view
    _service, _view = service, view


def get_sync_service() -> MemorySyncService:
    if _service is None:
        raise RuntimeError("memory sync service not initialised")
    return _service


def get_sync_view() -> MemorySyncView:
    if _view is None:
        raise RuntimeError("memory sync view not initialised")
    return _view
