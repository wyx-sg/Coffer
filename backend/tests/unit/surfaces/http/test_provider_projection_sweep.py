"""The boot hook that heals drifted provider projection.

The heal itself is covered in
``tests/unit/application/provider/test_projection_boot_heal.py``; what matters
here is that boot actually runs it and that a machine with an odd agent config
still boots. The lifespan hands the heal in explicitly (it is what
``wire_provider_kind`` returns), so the tests do the same.
"""

from __future__ import annotations

from coffer.surfaces.http.provider_wiring import run_provider_projection_sweep


class _Reconcile:
    def __init__(self, result: list[str] | Exception) -> None:
        self._result = result
        self.calls = 0

    async def heal(self) -> list[str]:
        self.calls += 1
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


async def test_boot_runs_the_heal() -> None:
    reconcile = _Reconcile([])

    await run_provider_projection_sweep(reconcile)

    assert reconcile.calls == 1, "a flag the agent contradicts only heals if boot asks"


async def test_a_reported_problem_does_not_fail_boot() -> None:
    await run_provider_projection_sweep(
        _Reconcile(["claude-code: config dir missing"])
    )  # logged, not raised


async def test_a_raising_heal_does_not_fail_boot() -> None:
    """An unreadable or unwritable agent config is somebody else's file being
    odd — never a reason for the daemon not to come up."""
    await run_provider_projection_sweep(_Reconcile(PermissionError("settings.json")))
