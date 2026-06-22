"""DI singleton for the transcript-distillation service (Spec 007 extension — ADR-020).

Extracted from ``surfaces/http/dependencies.py`` to keep that file under the
400-line limit.
"""

from __future__ import annotations

from typing import Any

_distill_service: Any | None = None
_distill_batch_service: Any | None = None


def set_distill_service(svc: Any) -> None:
    """Called by the composition root once on startup."""
    global _distill_service
    _distill_service = svc


def get_distill_service() -> Any:
    """FastAPI Depends() target — actual type is TranscriptDistillationService."""
    if _distill_service is None:
        raise RuntimeError("distill service not initialised")
    return _distill_service


def set_distill_batch_service(svc: Any) -> None:
    """Called by the composition root once on startup."""
    global _distill_batch_service
    _distill_batch_service = svc


def get_distill_batch_service() -> Any:
    """FastAPI Depends() target — actual type is DistillBatchService."""
    if _distill_batch_service is None:
        raise RuntimeError("distill batch service not initialised")
    return _distill_batch_service


def get_distill_batch_service_optional() -> Any | None:
    """Like :func:`get_distill_batch_service` but returns ``None`` when the
    service is not wired (so the list endpoint degrades to no status overlay
    instead of failing in tests / minimal apps)."""
    return _distill_batch_service
