"""``knowledge`` Kind wiring for the composition root.

One kind, one set of hooks — the union of what the two former faces had:

- ``on_update_config`` re-indexes when a retrieval or chunking field changes.
  The files are truth (ADR files-as-truth-sqlite-retrieval), so the index is
  always rebuildable and never the thing that must be migrated.
- ``on_delete`` is async so ``ResourceService`` awaits the on-disk teardown
  before the Resource row is gone.

There is no ``credential_ref_extractor``. Both faces used to extract an
embedding API-key ref from their config; embedding is now resolved through the
installation-wide config, so there is no per-scope credential to probe.
"""

from __future__ import annotations

import logging
from typing import Any

from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.knowledge.document import KIND_KNOWLEDGE
from coffer.domain.knowledge.scope_config import KnowledgeConfig
from coffer.domain.resource import Kind, ResourceRef

_logger = logging.getLogger(__name__)

#: Config fields whose change requires re-indexing the scope — the union of the
#: two former faces' lists, minus the embedding fields they both carried (those
#: are gone from the config). ``auto_update_sources`` is deliberately absent:
#: toggling it must not re-chunk.
_REINDEX_FIELDS = ("retrieval_modes", "chunk_size", "chunk_overlap")


def make_knowledge_kind(service: KnowledgeService) -> Kind:
    """Construct the ``knowledge`` Kind with its lifecycle hooks."""

    async def _on_delete(ref: ResourceRef) -> None:
        try:
            await service.cleanup_scope(ref.name)
        except Exception:
            # The Resource row deletion proceeds; orphaned files/rows deserve a
            # signal rather than silent accumulation.
            _logger.warning(
                "knowledge.on_delete.cleanup_failed",
                extra={"scope": ref.name},
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
            new_config = KnowledgeConfig.model_validate(after)
            await service.reindex_scope(scope_name=ref.name, config=new_config)
        except Exception:
            # The config update itself still proceeds; a transient rebuild
            # failure is recoverable by re-applying the config PATCH.
            _logger.warning(
                "knowledge.on_update_config.reindex_failed",
                extra={"scope": ref.name},
                exc_info=True,
            )

    return Kind(
        name=KIND_KNOWLEDGE,
        display_name="Knowledge",
        config_schema=KnowledgeConfig,
        on_delete=_on_delete,
        on_update_config=_on_update_config,
    )
