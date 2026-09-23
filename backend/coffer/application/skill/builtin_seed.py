"""Seeding Coffer's own skill into the master store as a real skill resource.

Coffer ships a manual for itself and keeps it in the same place every other
skill lives: one master folder under ``~/.coffer/skills/``, one ``skill``
resource row, delivered by the same predicate and the same links as any
imported skill. It is not a second delivery mechanism bolted beside the first,
which is what the rendered knowledge skill used to be — its own writer, its own
per-agent copies, invisible to the skills surface, unreachable by scope, and
outside every piece of machinery (drift verification, repair, reclaim) the skill
kind already had.

What makes it Coffer's rather than the user's is the ``builtin`` source on its
config: the folder's bytes are rewritten from the running build at every boot
and whenever the knowledge catalogue moves, so an edit to it does not survive,
and deleting it is refused (the skill kind's ``validate_delete``). Everything
else about it is ordinary — it can be disabled, and its scope can be narrowed,
because those are the owner's decisions about reach and this module has no
opinion on them.

The text arrives already rendered. This module never asks what is in it: the
renderer lives with the knowledge layer, the two kinds may not import each other
(import-linter's cross-kind fences), and the composition root is what joins
them. Like ``binding_ops`` and ``lifecycle_ops``, the functions here are
conceptually private to the skill subpackage and reach into ``SkillService``'s
own attributes.

Seeding never raises. A failure here leaves the vault working — every other
skill still delivers, and the manual is one boot away — so it must not be able
to fail a startup.
"""

from __future__ import annotations

import logging
import pathlib
import tempfile
from typing import TYPE_CHECKING

from coffer.domain.audit import AuditEventType
from coffer.domain.skill.builtin import is_builtin
from coffer.domain.skill.config import SkillConfig
from coffer.domain.skill.source import BuiltinSource
from coffer.domain.skill.validator import ValidationFailure, validate_skill_folder

if TYPE_CHECKING:
    from coffer.application.skill.service import SkillService
    from coffer.domain.resource import Resource

logger = logging.getLogger(__name__)

#: Audited actor for the seed, matching the other unattended boot work
#: (``boot_reconcile.BOOT_ACTOR``): this is Coffer acting, not a person.
SEED_ACTOR = "system"


class BuiltinSkillSeed:
    """Writes Coffer's generated skill into the master store and registers it."""

    def __init__(self, *, skill_service: SkillService) -> None:
        self._skills = skill_service

    async def seed(self, *, name: str, text: str) -> bool:
        """Put ``text`` behind skill ``name``; return whether anything changed.

        Safe to call on a timer and at every boot: when the master folder
        already holds exactly this text and the row agrees with it, nothing is
        written and nothing is audited. Delivery is reconciled either way,
        because a machine that received the row through a converge round has
        the master and the row but has never linked it into an agent.
        """
        try:
            changed = await self._write(name=name, text=text)
        except Exception:
            logger.warning("skill.builtin_seed.failed", extra={"skill": name}, exc_info=True)
            return False
        try:
            await self._deliver(name)
        except Exception:
            logger.warning(
                "skill.builtin_seed.deliver_failed", extra={"skill": name}, exc_info=True
            )
        return changed

    async def _write(self, *, name: str, text: str) -> bool:
        service = self._skills
        paths = service._store.paths_for(name)
        row = await self._row(name)
        if row is not None and _unchanged(paths.skill_md, text):
            return False

        with tempfile.TemporaryDirectory() as tmp:
            staged = pathlib.Path(tmp) / name
            staged.mkdir(parents=True)
            (staged / "SKILL.md").write_text(text, encoding="utf-8")
            validation = validate_skill_folder(staged, size_limit_bytes=service._size_limit)
            if isinstance(validation, ValidationFailure):
                # Coffer generated this text, so a validation failure is a
                # defect in the renderer, not bad input. Say so and leave
                # whatever is already on disk alone rather than replacing a
                # working manual with a broken one.
                logger.error(
                    "skill.builtin_seed.invalid",
                    extra={"skill": name, "reason": validation.reason},
                )
                return False
            meta = {"name": name, "source": {"type": BuiltinSource().type}}
            if service._store.exists(name):
                service._store.atomic_replace(src=staged, name=name, meta=meta)
            else:
                service._store.copy_in(src=staged, name=name, meta=meta)

        config = SkillConfig(
            source=BuiltinSource(),
            # The frontmatter's ``name`` is deliberately not stored: it is the
            # row's ``name``, and ``_write`` was handed that name to begin with.
            skill_md_description=validation.frontmatter.description,
            version_hash=validation.skill_md_sha256,
            # Deliberately null: a timestamp differs on every machine and the
            # config converges, so storing one would make two vaults disagree
            # forever (see ``domain.skill.source.BuiltinSource``).
            last_synced_from_source_at=None,
        ).model_dump(mode="json")

        # Both branches hand the audit the row they just wrote rather than a
        # label to look one up from: ``register`` mints the identity and
        # returns it, ``update_config`` returns the row as it now stands, and
        # neither answer can go stale between the write and the record.
        if row is None:
            seeded = await service._rs.register(
                kind="skill",
                name=name,
                config=config,
                description=validation.frontmatter.description,
                actor=SEED_ACTOR,
                allow_lifecycle_kind=True,  # creation seam: master folder written above
            )
            event = AuditEventType.SKILL_IMPORTED
        else:
            seeded = await service._rs.update_config(
                row.uid,
                new_config=config,
                actor=SEED_ACTOR,
                description=validation.frontmatter.description,
                allow_lifecycle_kind=True,  # creation seam: master folder written above
            )
            event = AuditEventType.SKILL_UPDATED
        await service._audit.record(
            event.value,
            resource=seeded,
            actor=SEED_ACTOR,
            details={"version_hash": validation.skill_md_sha256, "builtin": True},
        )
        return True

    async def _row(self, name: str) -> Resource | None:
        """The seeded row, if this machine already has one.

        By NAME, which everything else inside the daemon has stopped doing —
        and rightly here, because the seeder has no uid to start from. It is
        handed a name the running build generates, and whether some earlier
        boot already minted a row for it is precisely the question. Absence is
        an answer (first boot on this machine), not a failure, so this asks
        ``find_by_name`` rather than catching a ``ResourceNotFound``.
        """
        return await self._skills._rs.find_by_name("skill", name)

    async def _deliver(self, name: str) -> None:
        """Reconcile every agent's delivered set, so the new row lands."""
        for agent in await self._skills.list_agents():
            failures = await self._skills.apply_scope_for_agent(agent.name, actor=SEED_ACTOR)
            for failure in failures:
                logger.warning(
                    "skill.builtin_seed.delivery_conflict",
                    extra={"skill": name, "agent": agent.name, "detail": failure},
                )


def _unchanged(skill_md: pathlib.Path, text: str) -> bool:
    """Whether the master already holds exactly this text."""
    try:
        return skill_md.read_text(encoding="utf-8") == text
    except OSError:
        return False


#: Re-exported so the skill layer has one name for the question. The predicate
#: itself lives in ``domain.skill.builtin``: the kind, the surfaces and this
#: module all ask it, and a copy per caller is how two of them end up
#: disagreeing about what "Coffer's own" means.
__all__ = ["SEED_ACTOR", "BuiltinSkillSeed", "is_builtin"]
