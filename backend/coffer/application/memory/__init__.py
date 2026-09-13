"""Application layer for the ``memory`` resource kind (spec memory).

Ties the two finished native-memory readers to the derived, project-
partitioned fact store: :class:`MemoryService.aggregate` reads, files and
writes; :func:`make_memory_kind` wires the ``memory`` Resource kind's
lifecycle. Delivery (FR-050..055) and the developer's overrides
(``application.memory.overrides``) are separate concerns and are not
re-exported here.
"""

from coffer.application.memory.aggregate import (
    AgentSource,
    AgentSourceResolver,
    AggregationResult,
    SourceFailure,
)
from coffer.application.memory.kind import make_memory_kind
from coffer.application.memory.service import (
    KIND_MEMORY,
    MemoryPartitionConfig,
    MemoryService,
    PartitionSummary,
)

__all__ = [
    "KIND_MEMORY",
    "AgentSource",
    "AgentSourceResolver",
    "AggregationResult",
    "MemoryPartitionConfig",
    "MemoryService",
    "PartitionSummary",
    "SourceFailure",
    "make_memory_kind",
]
