"""Boot heal for skill-delivery drift that accumulates while the daemon is down.

Coffer delivers skills as symlinks/junctions into each agent's own skills
directory. Reconciliation today fires on agent registration, a skill's
enable-scope change, and sync import — never on its own while the daemon is
simply not running. A symlink broken or overwritten in that window (an
agent's installer rewriting its skills dir, a user tidying files, a restore
from backup) stayed broken forever: nothing else re-checks it, and the only
way to notice was a person opening the UI and clicking a manual "repair"
button — which the live audit log shows nobody ever did (zero
``skill_drift_remediated`` events in its whole history).

This module closes that gap the same way ``application/provider/boot_reconcile``
closes the analogous one for provider projections: run the existing, already
opt-in-safe repair once at every boot, so drift self-heals unattended instead
of waiting for a click that never comes.

**Scope is unchanged, only the trigger is new.** ``SkillService.repair_drift``
already restricts itself to the drift kinds that are safe to fix without
asking anyone (see ``verify_ops._REPAIRABLE_KINDS``): a missing link is simply
recreated, and a tampered link is renamed aside to a uniquely-suffixed backup
before recreating — never deleted, never overwritten in place. Kinds that
would clobber foreign content or that have nothing left to re-deliver from
(``REPLACED_WITH_REGULAR``, ``MISSING_MASTER``, ``ORPHAN_MASTER``) are left
alone by ``repair_drift`` itself; this heal does not loosen that boundary, it
only calls the same function earlier.
"""

from __future__ import annotations

import logging
from typing import Protocol as _Protocol

from coffer.domain.skill.drift import RepairResult

logger = logging.getLogger(__name__)

#: The actor recorded for repairs this heal makes, matching the other
#: automatic, no-human-in-the-loop actors already in the audit trail
#: (``credential_migration``'s startup move, the skill kind's own
#: registration-time ``apply_scope_for_agent`` reconciliation): "system", not
#: the user-facing default "api".
BOOT_ACTOR = "system"


class _SkillServicePort(_Protocol):
    async def repair_drift(self, *, actor: str) -> RepairResult: ...


class SkillDriftBootHeal:
    """Runs ``SkillService.repair_drift()`` once at daemon startup."""

    def __init__(self, *, skill_service: _SkillServicePort) -> None:
        self._skills = skill_service

    async def heal(self) -> list[str]:
        """Repair what's safely repairable; describe what isn't.

        Returns one human-readable note per repaired entry and one per
        residual entry that still needs attention. Residual drift now has no
        UI surface to notice it from — this log line is the only signal left,
        so it names the skill, the agent, the drift kind, and the on-disk
        path a person would need to go look at.
        """
        result = await self._skills.repair_drift(actor=BOOT_ACTOR)
        notes: list[str] = []
        for entry in result.remediated:
            notes.append(
                f"{entry.skill_name}/{entry.agent_name}: repaired {entry.kind.value} "
                f"at {entry.target_path}"
            )
        for entry in result.remaining.entries:
            notes.append(
                f"{entry.skill_name}/{entry.agent_name}: residual {entry.kind.value} at "
                f"{entry.target_path} — {entry.suggested_remedy}"
            )
        return notes


__all__ = ["BOOT_ACTOR", "SkillDriftBootHeal"]
