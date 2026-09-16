"""The ``memory`` Kind for the composition root.

Mirrors ``application/knowledge/kind.py``: a partition is a directory as much
as it is a Resource row, so ``generic_create_allowed`` is False and
``MemoryService.aggregate`` opts into creating one explicitly
(``allow_lifecycle_kind=True``, CODE-REG) rather than the generic
``POST /resources`` path being able to conjure a directory-less row.

``supports_scope`` is True because per-agent delivery is the entire reason a
partition is a Resource at all (spec memory FR-014) — without it there would
be nothing for the framework's scope to narrow.

``converges`` is False, and this is the only kind that sets it (spec memory
FR-023). A partition row is derived from the agents installed on THIS machine,
so publishing it to the sync remote puts on the second machine a partition
naming a project root it may not have, with no facts behind it — the derived
tree under ``~/.coffer/memory/`` is not mirrored either — until that machine's
own next pass recomputes it away. FR-023 names that exact sequence as the
reason the layer must not converge; the flag is what makes the sync layer
honour it, and it is declared here because it is a fact about this kind rather
than a case for the exporter to special-case.
"""

from __future__ import annotations

import logging

from coffer.application.memory.service import KIND_MEMORY, MemoryPartitionConfig, MemoryService
from coffer.domain.resource import Kind, ResourceRef

_logger = logging.getLogger(__name__)


def make_memory_kind(service: MemoryService) -> Kind:
    async def _on_delete(ref: ResourceRef) -> None:
        try:
            await service.cleanup_partition(ref.name)
        except Exception:
            # The row deletion proceeds either way; an orphaned directory
            # deserves a signal rather than silent accumulation.
            _logger.warning(
                "memory.on_delete.cleanup_failed",
                extra={"partition": ref.name},
                exc_info=True,
            )

    return Kind(
        name=KIND_MEMORY,
        display_name="Memory",
        config_schema=MemoryPartitionConfig,
        on_delete=_on_delete,
        generic_create_allowed=False,
        supports_scope=True,
        converges=False,
    )
