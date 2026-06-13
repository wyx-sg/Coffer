"""DI singleton for the transcript-distillation service (Spec 007 extension — ADR-020).

Extracted from ``surfaces/http/dependencies.py`` to keep that file under the
400-line limit.
"""

from __future__ import annotations

from typing import Any

_distill_service: Any | None = None


def set_distill_service(svc: Any) -> None:
    """Called by the composition root once on startup."""
    global _distill_service
    _distill_service = svc


def get_distill_service() -> Any:
    """FastAPI Depends() target — actual type is TranscriptDistillationService."""
    if _distill_service is None:
        raise RuntimeError("distill service not initialised")
    return _distill_service
