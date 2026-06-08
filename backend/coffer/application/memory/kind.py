"""``memory`` Kind wiring for the composition root (spec 007 redesign).

No mem0, no LLM, no immutability lock. The embedding model is mutable — a change
re-embeds the store on the next index (lazy, files are truth), so no
``on_update_config`` rejection is needed. The ``on_delete`` hook is async so
``ResourceService`` awaits the on-disk teardown before the Resource row is gone.
"""

from __future__ import annotations

import contextlib

from coffer.application.memory.service import MemoryService
from coffer.domain.memory.config import MemoryStoreConfig
from coffer.domain.resource import Kind, ResourceRef


def make_memory_kind(service: MemoryService) -> Kind:
    """Construct the ``memory`` Kind with lifecycle hooks."""

    async def _on_delete(ref: ResourceRef) -> None:
        with contextlib.suppress(Exception):
            await service.cleanup_store(ref.name)

    return Kind(
        name="memory",
        display_name="Memory Store",
        config_schema=MemoryStoreConfig,
        on_delete=_on_delete,
    )
