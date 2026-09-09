"""The boot hook that heals drifted provider projection.

The heal itself is covered in
``tests/unit/application/providers/test_projection_boot_heal.py``; what matters
here is that boot actually runs it and that a machine with an odd agent config
still boots.
"""

from __future__ import annotations

from fastapi import FastAPI

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
    app = FastAPI()
    reconcile = _Reconcile([])
    app.state.provider_projection_heal = reconcile

    await run_provider_projection_sweep(app)

    assert reconcile.calls == 1, "a flag the agent contradicts only heals if boot asks"


async def test_a_reported_problem_does_not_fail_boot() -> None:
    app = FastAPI()
    app.state.provider_projection_heal = _Reconcile(["claude-code: config dir missing"])

    await run_provider_projection_sweep(app)  # logged, not raised


async def test_a_raising_heal_does_not_fail_boot() -> None:
    """An unreadable or unwritable agent config is somebody else's file being
    odd — never a reason for the daemon not to come up."""
    app = FastAPI()
    app.state.provider_projection_heal = _Reconcile(PermissionError("settings.json"))

    await run_provider_projection_sweep(app)


async def test_an_app_without_the_provider_kind_is_a_no_op() -> None:
    await run_provider_projection_sweep(FastAPI())
