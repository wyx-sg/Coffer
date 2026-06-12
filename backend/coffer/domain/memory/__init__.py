"""Domain types for the `memory` resource kind (spec 007 redesign).

The retrieval ports + ``MemoryHit`` live in the shared
``coffer.domain.knowledge`` substrate; this package holds the memory-specific
config, fact, and scope value objects.
"""

from coffer.domain.knowledge.retrieval import MemoryHit
from coffer.domain.memory.config import MemoryStoreConfig
from coffer.domain.memory.fact import MemoryFact
from coffer.domain.memory.scope import MemoryScope, ResolvedScope

__all__ = [
    "MemoryFact",
    "MemoryHit",
    "MemoryScope",
    "MemoryStoreConfig",
    "ResolvedScope",
]
