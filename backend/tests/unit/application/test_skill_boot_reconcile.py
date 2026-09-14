"""Unit coverage for the skill-drift boot heal.

Integration coverage (a real broken symlink, a real audit row) lives in
``tests/integration/application/test_skill_service.py``; what matters here is
the heal's own contract: it calls ``repair_drift`` with the boot actor and
turns the result into notes a person can find in the daemon log — one line
per repaired entry, one line per entry still needing attention.
"""

from __future__ import annotations

from coffer.application.skill.boot_reconcile import BOOT_ACTOR, SkillDriftBootHeal
from coffer.domain.skill.drift import DriftEntry, DriftKind, DriftReport, RepairResult


def _entry(kind: DriftKind, *, skill: str = "s", agent: str = "a") -> DriftEntry:
    return DriftEntry(
        skill_name=skill,
        agent_name=agent,
        kind=kind,
        target_path=f"/agents/{agent}/skills/{skill}",
        suggested_remedy="fix it",
    )


class _SkillService:
    def __init__(self, result: RepairResult) -> None:
        self._result = result
        self.calls: list[str] = []

    async def repair_drift(self, *, actor: str) -> RepairResult:
        self.calls.append(actor)
        return self._result


async def test_heal_uses_the_boot_actor_not_a_user_actor() -> None:
    svc = _SkillService(RepairResult(remediated=[], remaining=DriftReport()))
    heal = SkillDriftBootHeal(skill_service=svc)

    await heal.heal()

    assert svc.calls == [BOOT_ACTOR]
    assert BOOT_ACTOR == "system", "matches the other automatic, no-human actors in the audit log"


async def test_repaired_entries_are_noted() -> None:
    entry = _entry(DriftKind.MISSING_LINK, skill="s-1", agent="claude-code")
    svc = _SkillService(RepairResult(remediated=[entry], remaining=DriftReport()))
    heal = SkillDriftBootHeal(skill_service=svc)

    notes = await heal.heal()

    assert len(notes) == 1
    assert "s-1" in notes[0] and "claude-code" in notes[0] and "missing_link" in notes[0]


async def test_residual_drift_is_noted_for_someone_to_find() -> None:
    """Unsafe-to-auto-repair drift (e.g. a foreign directory occupying the
    link path) is left on disk by ``repair_drift`` itself — this heal must
    not silence it, since the manual "repair" button is going away and this
    log line is the only place left to notice it."""
    entry = _entry(DriftKind.REPLACED_WITH_REGULAR, skill="s-2", agent="codex")
    report = DriftReport(entries=[entry])
    svc = _SkillService(RepairResult(remediated=[], remaining=report))
    heal = SkillDriftBootHeal(skill_service=svc)

    notes = await heal.heal()

    assert len(notes) == 1
    assert "s-2" in notes[0] and "codex" in notes[0] and "replaced_with_regular" in notes[0]
    assert "fix it" in notes[0], "the suggested remedy must travel into the log line"


async def test_no_drift_at_all_is_a_quiet_no_op() -> None:
    svc = _SkillService(RepairResult(remediated=[], remaining=DriftReport()))
    heal = SkillDriftBootHeal(skill_service=svc)

    assert await heal.heal() == []
