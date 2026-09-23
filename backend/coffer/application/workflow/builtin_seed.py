"""Putting Coffer's own workflow into a vault that has never had one (spec
workflow "Seed one built-in template").

The shape is ``application.skill.builtin_seed``'s: a boot-time class that puts
a resource Coffer ships into the same tables, through the same write path and
with the same audit trail as anything the developer registers themselves. It
differs on exactly one question, and deliberately.

**The skill seed re-asserts; this one does not.** Coffer's manual is derived
output — rewritten from the running build at every boot, and refused a delete —
because a stale manual describes a Coffer that is not there. A workflow is the
opposite: "Seed one built-in template" says the developer may edit or delete
this template "like any other", so from the moment the row exists it is theirs.
Re-writing it every boot would overwrite their edits; re-creating it after a
delete would argue with them. So this seeds once and then stops having an
opinion.

"Once" needs a record that outlives the row, because the three ways the
developer can make the row stop matching what was seeded — delete, rename,
disable — all leave a vault that looks unseeded to a naive check. That record
is the :class:`SeedRecord` port: one bit, per machine, written the first time
this vault is known to hold the built-in. Machine-local on purpose, because
seeding is a boot action of a machine, not a fact about the vault; a second
machine that receives the row through a converge round reads it as already
present and records the bit without writing anything.

Nothing here may fail a startup. A vault whose seed did not land still works —
the developer writes their own template, or the next boot tries again.
"""

from __future__ import annotations

import logging
from typing import Protocol

from coffer.application.resource_service import ResourceService
from coffer.application.workflow.kind import KIND_WORKFLOW
from coffer.domain.workflow.builtin import (
    BUILTIN_TEMPLATE_DESCRIPTION,
    BUILTIN_TEMPLATE_NAME,
    BUILTIN_TEMPLATE_UID,
    builtin_template_config,
)

logger = logging.getLogger(__name__)

#: Audited actor for the seed, matching the other unattended boot work
#: (``skill.builtin_seed.SEED_ACTOR``, ``skill.boot_reconcile.BOOT_ACTOR``):
#: this is Coffer acting, not a person.
SEED_ACTOR = "system"


class SeedRecord(Protocol):
    """Whether this machine has already seen the built-in template.

    Two methods and no argument between them, because the whole state is one
    bit. It is a port rather than a file path so the application layer keeps
    its hands off the filesystem (CODE-005) and so a test can prove the
    "do not resurrect" rule without a home directory.
    """

    def seen(self) -> bool:
        """True once :meth:`mark` has been called on this machine, ever."""

    def mark(self) -> None:
        """Record that this vault holds — or has held — the built-in."""


class BuiltinWorkflowSeed:
    """Registers the built-in template the first time, and only the first time."""

    def __init__(self, *, resources: ResourceService, record: SeedRecord) -> None:
        self._resources = resources
        self._record = record

    async def seed(self) -> bool:
        """Seed if this vault has never had the built-in; return whether it did.

        Never raises. Every failure mode here — an unregistered kind, a name
        the developer has taken, a database that will not write — is one the
        vault survives, and none of them is worth refusing to start over.
        """
        try:
            return await self._seed()
        except Exception:
            logger.warning("workflow.builtin_seed.failed", exc_info=True)
            return False

    async def _seed(self) -> bool:
        if self._record.seen():
            return False

        rows = await self._resources.list(kind=KIND_WORKFLOW)
        # Two ways the built-in can already be here without this machine having
        # seeded it: another machine did and the row converged, or the developer
        # has a template of their own under this name. Both are answered the
        # same way — record the bit and leave everything alone — because in
        # neither case is there anything to add, and in the second the row is
        # not ours to touch. Matching on the uid as well as the name is what
        # makes a rename stop the seed rather than duplicate it.
        if any(r.uid == BUILTIN_TEMPLATE_UID or r.name == BUILTIN_TEMPLATE_NAME for r in rows):
            self._record.mark()
            return False

        await self._resources.register(
            kind=KIND_WORKFLOW,
            name=BUILTIN_TEMPLATE_NAME,
            config=builtin_template_config(),
            actor=SEED_ACTOR,
            description=BUILTIN_TEMPLATE_DESCRIPTION,
            # The identity is fixed rather than minted: see BUILTIN_TEMPLATE_UID.
            uid=BUILTIN_TEMPLATE_UID,
        )
        # After the write, so a registration that raised is retried next boot
        # rather than recorded as done. The reverse order would lose the
        # built-in to one transient database error, permanently.
        self._record.mark()
        return True


__all__ = ["SEED_ACTOR", "BuiltinWorkflowSeed", "SeedRecord"]
