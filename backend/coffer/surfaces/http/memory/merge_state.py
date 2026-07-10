"""DI singletons for the AI-assisted store merge (spec 007, FR-056-059).

Mirrors ``organize_state.py``. Two registrations:

- ``set_store_consolidator`` — ``wire_memory_kind`` hands over the SAME
  :class:`StoreConsolidator` instance the resolve-time adoption uses, so an
  explicit merge and an adoption serialize on one lock (FR-057).
- ``set_merge_service`` — the composition root (``merge_wiring.py``)
  registers the :class:`StoreMergeService`; the merge routes reach it via
  ``get_merge_service``.
"""

from __future__ import annotations

from typing import Any

_store_consolidator: Any | None = None
_merge_service: Any | None = None


def set_store_consolidator(consolidator: Any) -> None:
    """Called by ``wire_memory_kind`` once on startup."""
    global _store_consolidator
    _store_consolidator = consolidator


def get_store_consolidator() -> Any:
    """Read by ``wire_merge`` — actual type is StoreConsolidator."""
    if _store_consolidator is None:
        raise RuntimeError("store consolidator not initialised")
    return _store_consolidator


def set_merge_service(svc: Any) -> None:
    """Called by the composition root once on startup."""
    global _merge_service
    _merge_service = svc


def get_merge_service() -> Any:
    """FastAPI Depends() target — actual type is StoreMergeService."""
    if _merge_service is None:
        raise RuntimeError("merge service not initialised")
    return _merge_service
