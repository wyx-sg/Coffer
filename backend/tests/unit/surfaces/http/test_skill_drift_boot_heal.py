"""The boot hook that heals drifted skill symlinks.

The heal itself is covered in
``tests/unit/application/test_skill_boot_reconcile.py``; what matters here is
that boot actually runs it and that a machine with unrepairable drift, or a
heal that blows up, still boots — mirrors
``tests/unit/surfaces/http/test_provider_projection_sweep.py`` for the
provider kind's analogous boot heal. The lifespan hands the heal in explicitly
(it is what ``wire_agent_and_skill_kinds`` returns), so the tests do the same.
"""

from __future__ import annotations

import pytest

from coffer.surfaces.http.agent_skill_wiring import run_skill_drift_boot_heal


class _Heal:
    def __init__(self, result: list[str] | Exception) -> None:
        self._result = result
        self.calls = 0

    async def heal(self) -> list[str]:
        self.calls += 1
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


async def test_boot_runs_the_heal() -> None:
    heal = _Heal([])

    await run_skill_drift_boot_heal(heal)

    assert heal.calls == 1, "drift only self-heals if boot actually asks"


async def test_a_reported_problem_does_not_fail_boot() -> None:
    await run_skill_drift_boot_heal(
        _Heal(["s/agent: residual replaced_with_regular"])
    )  # logged, not raised


@pytest.mark.acceptance(spec="skill-manager", scenario="a boot heal failure never blocks startup")
async def test_a_raising_heal_does_not_fail_boot() -> None:
    """A filesystem hiccup mid-repair is somebody else's disk being odd — never
    a reason for the daemon not to come up."""
    await run_skill_drift_boot_heal(_Heal(OSError("disk hiccup")))
