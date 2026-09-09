"""DI singleton for the async document batch (re-embed) service.

Kept apart from ``surfaces/http/dependencies.py`` to stay under the file-size
limit. The ``_optional`` accessor
lets the documents list/detail endpoints degrade to no status overlay (rather
than failing) when the batch service is not wired (minimal apps / route tests).
"""

from __future__ import annotations

from typing import Any

_batch_service: Any | None = None


def set_batch_service(svc: Any) -> None:
    """Called by the composition root once on startup."""
    global _batch_service
    _batch_service = svc


def get_batch_service() -> Any:
    """FastAPI Depends() target — actual type is KnowledgeBaseBatchService."""
    if _batch_service is None:
        raise RuntimeError("knowledge batch service not initialised")
    return _batch_service


def get_batch_service_optional() -> Any | None:
    """Like :func:`get_batch_service` but returns ``None`` when the service is
    not wired (so the list endpoint degrades to no status overlay instead of
    failing in tests / minimal apps)."""
    return _batch_service
