"""DI singleton for the transcript-history service (ADR-022).

Mirrors ``distill/state.py``: the composition root sets the service once on
startup; routes reach it through ``get_history_service`` as a FastAPI Depends().
"""

from __future__ import annotations

from typing import Any

_history_service: Any | None = None


def set_history_service(svc: Any) -> None:
    """Called by the composition root once on startup."""
    global _history_service
    _history_service = svc


def get_history_service() -> Any:
    """FastAPI Depends() target — actual type is HistoryService."""
    if _history_service is None:
        raise RuntimeError("history service not initialised")
    return _history_service
