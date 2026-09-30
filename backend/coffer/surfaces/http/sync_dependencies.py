"""The /api/v1/sync router and the sync service it serves, shared by
``sync_routes`` and ``sync_stop_routes`` (split for the file-size tier)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from coffer.application.sync.service import SyncService
from coffer.surfaces.http.auth import require_token

router = APIRouter(prefix="/api/v1/sync", tags=["sync"], dependencies=[Depends(require_token)])

_SERVICE: SyncService | None = None


def set_sync_service(service: SyncService | None) -> None:
    global _SERVICE
    _SERVICE = service


def get_sync_service() -> SyncService:
    if _SERVICE is None:
        raise RuntimeError("sync service not initialised")
    return _SERVICE


__all__ = ["get_sync_service", "router", "set_sync_service"]
