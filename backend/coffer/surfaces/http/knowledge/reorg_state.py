"""DI singleton for the notes tidy pass (the surviving ReorgService).

The composition root (``surfaces/http/reorg_wiring.py``) registers the service
once on startup. Two callers reach it from here: the manual
``POST /{name}/organize`` route, and the ``NotesTidyTrigger`` that arms the same
pass on idle and on an interval — one service, so a manual tidy and a background
one can never be two different behaviours.

A module-level singleton rather than a constructor argument because FastAPI's
``Depends`` needs a callable it can resolve per request, and the service is only
buildable once the provider and knowledge kinds are wired.
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
        raise RuntimeError("tidy service not initialised")
    return _reorg_service
