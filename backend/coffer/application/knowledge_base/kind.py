"""``knowledge_base`` Kind wiring for the composition root.

Redesign (spec 006): chunk params and the embedding model are **mutable**. The
``on_update_config`` hook no longer rejects those changes — it triggers a
re-chunk / re-embed of the corpus so the index matches the new config. The
``on_delete`` hook is async so ``ResourceService`` awaits the on-disk teardown
before the Resource row is removed.
"""

from __future__ import annotations

import logging
from typing import Any

from coffer.application.knowledge_base.service import KnowledgeBaseService
from coffer.domain.knowledge_base.config import KnowledgeBaseConfig
from coffer.domain.resource import Kind, ResourceRef

_logger = logging.getLogger(__name__)

# Config fields whose change requires re-indexing / re-embedding the corpus.
_REINDEX_FIELDS = ("chunk_size", "chunk_overlap", "enabled_modes", "embedding")


def make_kb_kind(service: KnowledgeBaseService) -> Kind:
    """Construct the ``knowledge_base`` Kind with lifecycle hooks."""

    async def _on_delete(ref: ResourceRef) -> None:
        try:
            await service.cleanup_kb(ref.name)
        except Exception:
            # The Resource row deletion proceeds; orphaned files/rows deserve a
            # signal rather than silent accumulation.
            _logger.warning(
                "kb.on_delete.cleanup_failed",
                extra={"kb": ref.name},
                exc_info=True,
            )

    async def _on_update_config(
        ref: ResourceRef,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> None:
        # Mutable: a chunk/embedding change re-indexes the corpus (not rejected).
        if not any(before.get(f) != after.get(f) for f in _REINDEX_FIELDS):
            return
        try:
            new_config = KnowledgeBaseConfig.model_validate(after)
            await service.reindex_with_config(kb_name=ref.name, config=new_config, actor="system")
        except Exception:
            # The config update itself still proceeds; a transient reindex
            # failure is recoverable via an explicit `coffer kb reindex`.
            _logger.warning(
                "kb.on_update_config.reindex_failed",
                extra={"kb": ref.name},
                exc_info=True,
            )

    return Kind(
        name="knowledge_base",
        display_name="Knowledge Base",
        config_schema=KnowledgeBaseConfig,
        on_delete=_on_delete,
        on_update_config=_on_update_config,
    )
