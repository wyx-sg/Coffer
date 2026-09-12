"""The ``knowledge`` Kind for the composition root.

A collection carries no config and no lifecycle beyond existing, so the kind is
almost all default. The two fields that are not:

- ``supports_scope`` is True, because per-agent authorization is the reason a
  collection is a Resource at all (spec knowledge FR-012). Without it a
  directory would not need the framework.
- ``generic_create_allowed`` is False, because a collection is a directory as
  much as a row: the generic ``POST /resources`` path would create the row with
  no folder behind it. ``KnowledgeService.create_collection`` opts in
  explicitly (CODE-REG), the same way the skill and agent kinds do.

There is no ``on_update_config`` — nothing in the config can change, because
there is nothing in the config.
"""

from __future__ import annotations

import logging

from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.domain.knowledge.config import KnowledgeConfig
from coffer.domain.resource import Kind, ResourceRef

_logger = logging.getLogger(__name__)


def make_knowledge_kind(service: KnowledgeService) -> Kind:
    async def _on_delete(ref: ResourceRef) -> None:
        try:
            await service.cleanup_collection(ref.name)
        except Exception:
            # The row deletion proceeds either way; an orphaned directory
            # deserves a signal rather than silent accumulation.
            _logger.warning(
                "knowledge.on_delete.cleanup_failed",
                extra={"collection": ref.name},
                exc_info=True,
            )

    return Kind(
        name=KIND_KNOWLEDGE,
        display_name="Knowledge",
        config_schema=KnowledgeConfig,
        on_delete=_on_delete,
        generic_create_allowed=False,
        supports_scope=True,
    )
