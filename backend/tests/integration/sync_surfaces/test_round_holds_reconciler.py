"""A sync round keeps the real reconciler's passes out until its own import
pass has run (spec vault-sync "Run the reconciler once after a round that
applied changes"; resource-framework "Converge what Coffer writes outside its database").

The checkout hints every resource it changed. Without the hold, the hinted
pass judges the vault before the round's import pass, under a trigger with
less warrant, and can undo a provider switch made on another machine.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path

import pytest

from coffer.application.reconcile.ports import Applied
from coffer.application.reconcile.reconciler import Reconciler
from coffer.domain.reconcile import (
    Changed,
    Decision,
    Difference,
    Disposition,
    Item,
    PlannedChange,
    Subject,
    Trigger,
)

from .harness import joined


class _Recorder:
    """A target that wants one item and notes the trigger of every pass."""

    name = "recorder"
    kinds = frozenset({"provider"})

    def __init__(self) -> None:
        self.triggers: list[Trigger] = []

    async def desired(self) -> Sequence[Item]:
        return [Item("one", Subject("provider", "uid-1", "One"), {"is_active": True})]

    async def observe(self) -> Sequence[Item]:
        return []

    def decide(self, differences: Sequence[Difference], trigger: Trigger) -> Sequence[Decision]:
        self.triggers.append(trigger)
        return [Decision(Disposition.REPORT, "recorded", "recorded") for _ in differences]

    async def apply(self, change: PlannedChange) -> Applied:
        raise AssertionError("never repairs")


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a round that applied changes runs one reconcile pass"
)
def test_no_hinted_pass_runs_before_the_rounds_import_pass(tmp_path: Path) -> None:
    mac, mini = joined(tmp_path, "Mac", "Mini")
    mac.put("resources/provider/uid-1.json", "{}\n")
    mac.round()

    async def scenario() -> list[Trigger]:
        reconciler = Reconciler(audit=None, period_seconds=3600, settle_seconds=0.05)  # type: ignore[arg-type]
        target = _Recorder()
        reconciler.register(target)
        loop = asyncio.get_running_loop()

        # What the resource store's commit listener does with a checkout.
        def on_commit(_result: object) -> None:
            loop.call_soon_threadsafe(reconciler.hint, Changed("provider", "uid-1"))

        mini.writer.add_listener(on_commit)

        async def import_pass() -> None:
            # The push is still in flight, well past the hint's settle window.
            await asyncio.sleep(0.4)
            await reconciler.run(trigger=Trigger.IMPORT)

        mini.service._hold = reconciler.hold
        mini.service._after_apply = import_pass
        serving = asyncio.create_task(reconciler.serve())
        try:
            record = await mini.service.run()
            assert record.applied
            await asyncio.sleep(0.4)  # let a held hint pass run once released
        finally:
            serving.cancel()
        return target.triggers

    triggers = asyncio.run(scenario())
    assert triggers[0] is Trigger.IMPORT
