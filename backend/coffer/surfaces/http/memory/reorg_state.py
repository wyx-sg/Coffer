"""DI singleton for the memory ReorgService (spec 007 — agentic reorg).

Mirrors ``surfaces/http/memory/organize_state.py``: the composition root
(``surfaces/http/reorg_wiring.py``) registers the service once on startup;
the ``reorg`` route reaches it via ``get_reorg_service``.
"""

from __future__ import annotations

from typing import Any

_reorg_service: Any | None = None


def set_reorg_service(svc: Any) -> None:
    """Called by the composition root once on startup."""
    global _reorg_service
    _reorg_service = svc


def get_reorg_service() -> Any:
    """FastAPI Depends() target — actual type is ReorgService."""
    if _reorg_service is None:
        raise RuntimeError("reorg service not initialised")
    return _reorg_service
