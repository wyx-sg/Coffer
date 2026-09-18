"""The ``knowledge`` Kind for the composition root.

A collection carries no config and no lifecycle beyond existing, so the kind is
almost all default. The one field that is not:

- ``generic_create_allowed`` is False, because a collection is a directory as
  much as a row: the generic ``POST /resources`` path would create the row with
  no folder behind it. ``KnowledgeService.create_collection`` opts in
  explicitly (CODE-REG), the same way the skill and agent kinds do.

Two defaults are worth naming, because an earlier design set them otherwise:

- ``supports_scope`` stays False: this kind carries **no per-agent reach**.
  Every enabled collection is served to every agent, and ``enabled`` is the
  only gate there is. A scope here would have been fiction rather than a
  narrowing — the skill Coffer delivers hands the agent the absolute knowledge
  root and tells it to grep the whole thing, so a collection kept out of one
  agent's catalogue was still a directory that agent could read. It was never
  used either: every ``knowledge`` row in the real vault had an empty scope.
- There is no ``on_update_config`` — nothing in the config can change, because
  there is nothing in the config.

``on_delete`` and ``on_enabled_changed`` both end by telling the service its
catalogue moved. The catalogue is carried by Coffer's own skill (FR-034), and
that skill is a file: switching a collection off changes nothing an agent can
see until the file is rewritten, so a re-render that waited for the next boot
would leave the agent reading a catalogue the owner had already changed.
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
        await service.catalogue_changed()

    async def _on_enabled_changed(ref: ResourceRef) -> None:
        await service.catalogue_changed()

    return Kind(
        name=KIND_KNOWLEDGE,
        display_name="Knowledge",
        config_schema=KnowledgeConfig,
        on_delete=_on_delete,
        # ``enabled`` is this kind's only switch, and it decides what the
        # delivered catalogue names — so it has to reach the file.
        on_enabled_changed=_on_enabled_changed,
        generic_create_allowed=False,
    )
