"""DI singleton for the async KB batch (re-embed) service.

Kept apart from ``surfaces/http/dependencies.py`` to stay under the file-size
limit, mirroring ``surfaces/http/distill/state.py``. The ``_optional`` accessor
lets the documents list/detail endpoints degrade to no status overlay (rather
than failing) when the batch service is not wired (minimal apps / route tests).
"""

from __future__ import annotations

from typing import Any

_kb_batch_service: Any | None = None


def set_kb_batch_service(svc: Any) -> None:
    """Called by the composition root once on startup."""
    global _kb_batch_service
    _kb_batch_service = svc


def get_kb_batch_service() -> Any:
    """FastAPI Depends() target — actual type is KnowledgeBaseBatchService."""
    if _kb_batch_service is None:
        raise RuntimeError("knowledge base batch service not initialised")
    return _kb_batch_service


def get_kb_batch_service_optional() -> Any | None:
    """Like :func:`get_kb_batch_service` but returns ``None`` when the service is
    not wired (so the list endpoint degrades to no status overlay instead of
    failing in tests / minimal apps)."""
    return _kb_batch_service
