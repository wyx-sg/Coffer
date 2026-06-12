"""Root of the domain error hierarchy.

Lives in its own module so per-feature error modules (e.g.
``coffer.domain.chat.errors``) can subclass ``CofferError`` without importing
``coffer.domain.errors`` — that module re-exports the feature errors at its
bottom, and a top-of-module import back into it would make the import order
between the two modules matter (importing the feature module first would
crash on the partially-initialized re-exporter).
"""

from __future__ import annotations


class CofferError(Exception):
    """Root of every domain-raised exception."""

    code: str = "INTERNAL_ERROR"
