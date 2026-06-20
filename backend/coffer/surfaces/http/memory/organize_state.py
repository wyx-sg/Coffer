"""DI singleton for the memory OrganizerService (spec 007 — internal organizer).

Mirrors ``surfaces/http/distill/state.py``: the composition root
(``surfaces/http/organize_wiring.py``) registers the service once on startup;
the ``organize`` route reaches it via ``get_organizer_service``.
"""

from __future__ import annotations

from typing import Any

_organizer_service: Any | None = None


def set_organizer_service(svc: Any) -> None:
    """Called by the composition root once on startup."""
    global _organizer_service
    _organizer_service = svc


def get_organizer_service() -> Any:
    """FastAPI Depends() target — actual type is OrganizerService."""
    if _organizer_service is None:
        raise RuntimeError("organizer service not initialised")
    return _organizer_service
