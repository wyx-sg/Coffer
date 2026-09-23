"""Application layer for the ``memory`` resource kind (spec memory).

Two passes over two directories, and one service where both meet the database.
:func:`~coffer.application.memory.aggregate.run_aggregation` reads the two
finished native-memory readers and writes what they said, verbatim, under each
partition's hidden ``.raw/``; the distil pass turns those entries into Coffer's
own notes and writes the index. :class:`MemoryService` drives both, registers
the partitions a pass files into, and is the one read path — ``notes/``, at
call time — that delivery and recall compose against.
:func:`make_memory_kind` wires the ``memory`` Resource kind's lifecycle.

Delivery and recall are separate concerns with their
own modules, and are not re-exported here.
"""

from coffer.application.memory.aggregate import (
    AgentSource,
    AgentSourceResolver,
    AggregationOutcome,
    AggregationResult,
    PartitionTouch,
    Placement,
    SourceFailure,
    run_aggregation,
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
    "AggregationOutcome",
    "AggregationResult",
    "MemoryPartitionConfig",
    "MemoryService",
    "PartitionSummary",
    "PartitionTouch",
    "Placement",
    "SourceFailure",
    "make_memory_kind",
    "run_aggregation",
]
