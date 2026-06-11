"""``memory`` Kind wiring for the composition root (spec 007 redesign).

No mem0, no LLM, no immutability lock. The embedding model is mutable — the
``on_update_config`` hook force-rebuilds the store's index (files are truth) so
facts written before the change are re-embedded under the new config. The
``on_delete`` hook is async so ``ResourceService`` awaits the on-disk teardown
before the Resource row is gone.
"""

from __future__ import annotations

import logging
from typing import Any

from coffer.application.memory.service import MemoryService
from coffer.domain.memory.config import MemoryStoreConfig
from coffer.domain.resource import Kind, ResourceRef

_logger = logging.getLogger(__name__)

# Config fields whose change requires re-indexing / re-embedding the store.
_REINDEX_FIELDS = (
    "retrieval_modes",
    "embedding_provider",
    "embedding_model",
    "embedding_base_url",
    "embedding_dimensions",
)


def make_memory_kind(service: MemoryService) -> Kind:
    """Construct the ``memory`` Kind with lifecycle hooks."""

    async def _on_delete(ref: ResourceRef) -> None:
        try:
            await service.cleanup_store(ref.name)
        except Exception:
            # The Resource row deletion proceeds; orphaned files/rows deserve a
            # signal rather than silent accumulation.
            _logger.warning(
                "memory.on_delete.cleanup_failed",
                extra={"store": ref.name},
                exc_info=True,
            )

    async def _on_update_config(
        ref: ResourceRef,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> None:
        if not any(before.get(f) != after.get(f) for f in _REINDEX_FIELDS):
            return
        try:
            new_config = MemoryStoreConfig.model_validate(after)
            await service.reindex_store(store_name=ref.name, config=new_config)
        except Exception:
            # The config update itself still proceeds; a transient rebuild
            # failure is recoverable by re-applying the config PATCH.
            _logger.warning(
                "memory.on_update_config.reindex_failed",
                extra={"store": ref.name},
                exc_info=True,
            )

    return Kind(
        name="memory",
        display_name="Memory Store",
        config_schema=MemoryStoreConfig,
        on_delete=_on_delete,
        on_update_config=_on_update_config,
    )
