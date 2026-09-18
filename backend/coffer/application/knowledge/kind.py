"""The ``knowledge`` Kind for the composition root.

A collection carries no config and no lifecycle beyond existing, so the kind is
almost all default. The two fields that are not, and both for the same reason —
a collection is a **directory** as much as it is a row:

- ``generic_create_allowed`` is False, because the generic ``POST /resources``
  path would create the row with no folder behind it.
  ``KnowledgeService.create_collection`` opts in explicitly (CODE-REG), the
  same way the skill and agent kinds do.
- ``on_rename`` moves that folder. The row's name is the directory's name, so
  a label that changes without the directory changing with it leaves the row
  pointing at nothing (ADR resource-identity-is-an-immutable-uid: "the three
  file-backed kinds get an ``on_rename`` hook ... that hook is the whole of
  what rename costs anywhere").

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
from coffer.domain.errors import ResourceAlreadyExists
from coffer.domain.knowledge.config import KnowledgeConfig
from coffer.domain.resource import Kind, Resource

_logger = logging.getLogger(__name__)


def make_knowledge_kind(service: KnowledgeService) -> Kind:
    async def _on_delete(resource: Resource) -> None:
        try:
            await service.cleanup_collection(resource.name)
        except Exception:
            # The row deletion proceeds either way; an orphaned directory
            # deserves a signal rather than silent accumulation.
            _logger.warning(
                "knowledge.on_delete.cleanup_failed",
                extra={"collection": resource.name},
                exc_info=True,
            )
        await service.catalogue_changed()

    async def _on_enabled_changed(resource: Resource) -> None:
        await service.catalogue_changed()

    async def _on_rename(resource: Resource, new_name: str) -> None:
        """Carry the collection's directory to the new label.

        The opposite failure policy from ``on_delete`` above, and deliberately
        so. A delete that leaves a directory behind costs disk and is logged;
        a *rename* that leaves the directory behind costs the collection — the
        row would point at ``~/.coffer/knowledge/<new>/``, the corpus would
        still be under ``<old>/``, and the layer reads the directory. So this
        hook lets its failure through, and because ``on_rename`` is pre-write
        the rename is abandoned with the row and the folder both untouched.

        The one failure it translates is the collision. ``rename_collection_dir``
        refuses to move onto an existing directory — the framework only checked
        that no *row* holds the new name, and a folder can be there without one
        — and that is the same answer as "the name is taken", so it is reported
        as the same error and gets the same 409 rather than a 500 naming a
        path.
        """
        try:
            await service.move_collection(resource.name, new_name)
        except FileExistsError as e:
            raise ResourceAlreadyExists(KIND_KNOWLEDGE, new_name) from e

    return Kind(
        name=KIND_KNOWLEDGE,
        display_name="Knowledge",
        config_schema=KnowledgeConfig,
        on_delete=_on_delete,
        on_rename=_on_rename,
        # ``enabled`` is this kind's only switch, and it decides what the
        # delivered catalogue names — so it has to reach the file.
        on_enabled_changed=_on_enabled_changed,
        generic_create_allowed=False,
    )
