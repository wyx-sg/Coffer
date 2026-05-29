"""Prunable-table registry — back-compat re-export shim.

The canonical home for these pure value types is now
``coffer.application.retention_registry`` (CODE-005: application code must
not import from infrastructure). This module re-exports the same names so
existing call sites at composition root and in infrastructure continue to
work unchanged.
"""

from __future__ import annotations

from coffer.application.retention_registry import (
    PrunableRegistry,
    PrunableTable,
    UnknownPrunableTable,
)

__all__ = ["PrunableRegistry", "PrunableTable", "UnknownPrunableTable"]
