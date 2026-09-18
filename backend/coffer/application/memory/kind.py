"""The ``memory`` Kind for the composition root.

Mirrors ``application/knowledge/kind.py``: a partition is a directory as much
as it is a Resource row, so ``generic_create_allowed`` is False and
``MemoryService.aggregate`` opts into creating one explicitly
(``allow_lifecycle_kind=True``, CODE-REG) rather than the generic
``POST /resources`` path being able to conjure a directory-less row.

``supports_scope`` is left at the Kind default of False, and a partition is a
Resource for three other things: its lifecycle (it is created by a pass and
deleted through the framework's own route), the repository identity its config
carries (FR-014), and its ``enabled`` flag — which is now the only gate on
what gets served.

It used to carry the framework's per-agent reach, and the reach was never
chosen: ``MemoryService._register_partition`` seeded it with "the agents this
partition was aggregated from", so on the maintainer's own vault the
``coffer`` partition came out scoped to ``claude-code`` alone — Codex, working
in the Coffer repository every day, was served no project memory whatsoever —
while the ``account*`` partitions came out scoped to ``codex`` and Claude Code
got nothing from them. That default defeated the layer's whole purpose: memory
aggregated from several agents exists precisely so each of them can read what
the others learned. It was never a boundary either, because a note is a file
the agent is handed the path to. So the reach is gone rather than
re-defaulted, and every enabled partition is served to every agent (FR-013).

``converges`` is False, and this is the only kind that sets it (spec memory
FR-019). A partition row is derived from the agents installed on THIS machine,
so publishing it to the sync remote puts on the second machine a partition
naming a repository it may not have cloned, with no notes behind it — the
derived tree under ``~/.coffer/memory/`` is not mirrored either — until that
machine's own next pass recomputes it away. FR-019 names that exact sequence as
the reason the layer must not converge; the flag is what makes the sync layer
honour it, and it is declared here because it is a property of this kind rather
than a case for the exporter to special-case.

``on_delete`` removes the whole partition directory — index, notes, retirement
record and ``.raw/`` — and that is safe for the same reason everything else
here is: the tree is derived, and the agents still hold what it was built from.
Deleting a partition is also the *only* answer to an unresolvable one (FR-016),
which is why it stays reachable rather than being hidden behind the pass.

``on_rename`` moves that same directory, because the row's name is the
directory's name (ADR resource-identity-is-an-immutable-uid). It is the only
hook here that can *refuse*, and it refuses twice: ``global`` is not renameable
at all, and a directory already sitting under the new name is a collision
rather than something to merge into. See the hook itself for why each of those
is a refusal instead of a best effort.
"""

from __future__ import annotations

import logging

from coffer.application.memory.service import KIND_MEMORY, MemoryPartitionConfig, MemoryService
from coffer.domain.errors import ConfigValidationError, ResourceAlreadyExists
from coffer.domain.memory.partition import GLOBAL_PARTITION
from coffer.domain.resource import Kind, Resource

_logger = logging.getLogger(__name__)


def make_memory_kind(service: MemoryService) -> Kind:
    async def _on_delete(resource: Resource) -> None:
        try:
            await service.cleanup_partition(resource.name)
        except Exception:
            # The row deletion proceeds either way; an orphaned directory
            # deserves a signal rather than silent accumulation.
            _logger.warning(
                "memory.on_delete.cleanup_failed",
                extra={"partition": resource.name},
                exc_info=True,
            )

    async def _on_rename(resource: Resource, new_name: str) -> None:
        """Carry the partition's directory to the new label.

        Two refusals, and both abort the rename with nothing moved — which is
        what a PRE-write hook is for.

        **``global`` cannot be renamed.** It is the one partition this layer
        names in code: aggregation files a personal entry or a directory inside
        no repository into ``GLOBAL_PARTITION``, and composing a session's
        context reads it by that name. Renaming the row would not move any of
        that — the very next pass would create a second, empty ``global``
        beside the renamed one and go on filling it, while the renamed
        partition kept notes nothing would ever deliver again. It is refused
        rather than made to work, because "``global`` is called global" is what
        every other module in the layer is entitled to assume.

        **A directory already under the new name is a collision.** The
        framework checked that no *row* holds the name, not that the filesystem
        is clear; ``store.rename_partition`` refuses to merge into what is
        there, and merging is the specific harm — two repositories' raw entries
        in one partition is exactly what keying on a repository (FR-014)
        exists to prevent, and the next pass would not undo it.
        """
        if resource.name == GLOBAL_PARTITION:
            raise ConfigValidationError(
                f"the {GLOBAL_PARTITION!r} partition cannot be renamed: the layer resolves it "
                "by that name, so a rename would leave its notes behind and start a new one"
            )
        try:
            await service.move_partition(resource.name, new_name)
        except FileExistsError as e:
            raise ResourceAlreadyExists(KIND_MEMORY, new_name) from e

    return Kind(
        name=KIND_MEMORY,
        display_name="Memory",
        config_schema=MemoryPartitionConfig,
        on_delete=_on_delete,
        on_rename=_on_rename,
        generic_create_allowed=False,
        converges=False,
    )
