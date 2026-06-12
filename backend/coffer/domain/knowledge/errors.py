"""Substrate-facing error names.

The canonical error classes live in :mod:`coffer.domain.errors` (one hierarchy
for the whole app). The data-models for specs 006/007 reference some of them
under ``domain/knowledge/errors`` and ``domain/memory``; this module re-exports
the substrate-relevant ones so importers can use the documented path.
"""

from __future__ import annotations

from coffer.domain.errors import (
    DocumentNotFound,
    EmbeddingUnavailable,
    EngineUnavailable,
    IngestRejected,
    KBNotFound,
    MemoryNotFound,
    MemoryRejected,
    MemoryStoreNotFound,
    ReconversionBlocked,
    ScopeUnresolved,
)

__all__ = [
    "DocumentNotFound",
    "EmbeddingUnavailable",
    "EngineUnavailable",
    "IngestRejected",
    "KBNotFound",
    "MemoryNotFound",
    "MemoryRejected",
    "MemoryStoreNotFound",
    "ReconversionBlocked",
    "ScopeUnresolved",
]
