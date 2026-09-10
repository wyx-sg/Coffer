"""Unit tests for ``NotesTidyTrigger`` — what decides *when* the tidy pass runs.

Two arming paths with different failure modes. The idle timer must coalesce a
burst of writes into ONE pass (each pass costs LLM calls) and must not fire at
all once the daemon is shutting down. The interval sweep must reach every scope,
including the ones the idle timer structurally cannot see, and must survive a
scope that blows up — it is a daemon-lifetime loop, so one bad scope may not end
it or escape into the caller.

The tidy pass itself is a fake here: this module is pure scheduling, and the
real pass is covered end-to-end in the integration tier.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from coffer.application.knowledge.tidy_trigger import NotesTidyTrigger

pytestmark = pytest.mark.asyncio


class _RecordingTidy:
    """A fake tidy pass: records the scopes it was asked to tidy."""

    def __init__(self, *, fails_on: set[str] | None = None) -> None:
        self.calls: list[str] = []
        self._fails_on = fails_on or set()

    async def reorg(self, *, scope_name: str) -> Any:
        self.calls.append(scope_name)
        if scope_name in self._fails_on:
            raise RuntimeError(f"tidy blew up on {scope_name}")
        return None


def _trigger(tidy: Any, scopes: list[str], **kw: Any) -> NotesTidyTrigger:
    async def list_scopes() -> list[str]:
        return list(scopes)

    return NotesTidyTrigger(tidy=tidy, list_scopes=list_scopes, **kw)


async def _settle(delay: float) -> None:
    """Give a pending idle timer comfortably longer than its delay to fire."""
    await asyncio.sleep(delay * 6)


# --- the idle path ----------------------------------------------------------


async def test_a_write_tidies_that_scope_after_the_quiet_spell() -> None:
    tidy = _RecordingTidy()
    trigger = _trigger(tidy, [], idle_delay_seconds=0.02)

    await trigger.on_change("global")
    assert tidy.calls == []  # not yet — the session may not be over

    await _settle(0.02)
    assert tidy.calls == ["global"]


async def test_a_burst_of_writes_coalesces_into_one_pass() -> None:
    """Each write re-arms the same timer. Ten writes in a session must cost one
    pass, not ten — the pass is an LLM loop."""
    tidy = _RecordingTidy()
    trigger = _trigger(tidy, [], idle_delay_seconds=0.05)

    for _ in range(10):
        await trigger.on_change("global")
        await asyncio.sleep(0.005)  # keeps re-arming inside the quiet window
    assert tidy.calls == []

    await _settle(0.05)
    assert tidy.calls == ["global"]


async def test_the_dirty_set_survives_re_arming_and_covers_every_touched_scope() -> None:
    """Re-arming cancels the timer, not the accounting: a write to a second
    scope inside the window must not drop the first scope's pending tidy."""
    tidy = _RecordingTidy()
    trigger = _trigger(tidy, [], idle_delay_seconds=0.05)

    await trigger.on_change("global")
    await asyncio.sleep(0.005)
    await trigger.on_change("project-01ABC")

    await _settle(0.05)
    assert sorted(tidy.calls) == ["global", "project-01ABC"]


async def test_the_dirty_set_is_cleared_so_an_untouched_scope_is_not_retidied() -> None:
    tidy = _RecordingTidy()
    trigger = _trigger(tidy, [], idle_delay_seconds=0.02)

    await trigger.on_change("global")
    await _settle(0.02)
    await trigger.on_change("project-01ABC")
    await _settle(0.02)

    assert tidy.calls == ["global", "project-01ABC"]


async def test_shutdown_drops_a_pending_timer_without_firing_it() -> None:
    """Nothing is lost by not firing — the next boot's catch-up sweep visits
    every scope — and a pass started during shutdown would race the teardown."""
    tidy = _RecordingTidy()
    trigger = _trigger(tidy, [], idle_delay_seconds=0.05)

    await trigger.on_change("global")
    await trigger.shutdown()
    await _settle(0.05)

    assert tidy.calls == []


async def test_shutdown_with_nothing_pending_is_a_clean_no_op() -> None:
    tidy = _RecordingTidy()
    trigger = _trigger(tidy, [], idle_delay_seconds=0.02)

    await trigger.shutdown()  # never armed

    assert tidy.calls == []


async def test_an_idle_pass_that_raises_does_not_escape_the_trigger() -> None:
    """The idle timer runs as a bare task: an exception would be swallowed by
    asyncio and silently kill the arming path."""
    tidy = _RecordingTidy(fails_on={"global"})
    trigger = _trigger(tidy, [], idle_delay_seconds=0.02)

    await trigger.on_change("global")
    await _settle(0.02)
    assert tidy.calls == ["global"]

    # The trigger still arms after the failure.
    await trigger.on_change("project-01ABC")
    await _settle(0.02)
    assert tidy.calls == ["global", "project-01ABC"]


# --- the interval path ------------------------------------------------------


async def test_the_sweep_visits_every_scope_starting_at_boot() -> None:
    """A catch-up pass runs immediately, before the first interval elapses —
    that is what catches a daemon restarted before its idle timer fired."""
    tidy = _RecordingTidy()
    trigger = _trigger(tidy, ["global", "project-01ABC", "team-notes"], interval_seconds=30.0)

    task = asyncio.create_task(trigger.run())
    await asyncio.sleep(0.05)
    trigger.stop()
    await asyncio.wait_for(task, timeout=1.0)

    assert tidy.calls == ["global", "project-01ABC", "team-notes"]


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="the tidy worker runs on boot and on an interval",
)
async def test_the_sweep_runs_at_boot_and_then_repeats_on_the_interval() -> None:
    tidy = _RecordingTidy()
    trigger = _trigger(tidy, ["global"], interval_seconds=0.05)

    task = asyncio.create_task(trigger.run())
    await asyncio.sleep(0.01)  # well inside the first interval
    assert tidy.calls == ["global"]  # the catch-up pass ran at boot

    await asyncio.sleep(0.16)
    trigger.stop()
    await asyncio.wait_for(task, timeout=1.0)

    assert len(tidy.calls) >= 3  # boot pass + at least two interval passes
    assert set(tidy.calls) == {"global"}


async def test_one_failing_scope_does_not_stop_the_others_or_the_loop() -> None:
    tidy = _RecordingTidy(fails_on={"project-01ABC"})
    trigger = _trigger(tidy, ["global", "project-01ABC", "team-notes"], interval_seconds=30.0)

    task = asyncio.create_task(trigger.run())
    await asyncio.sleep(0.05)
    trigger.stop()
    await asyncio.wait_for(task, timeout=1.0)  # the loop exited cleanly, not by raising

    assert tidy.calls == ["global", "project-01ABC", "team-notes"]


async def test_a_failing_scope_listing_skips_the_sweep_without_killing_the_loop() -> None:
    """The scope listing hits the database; a transient failure must cost one
    sweep, not the daemon's whole tidy schedule."""
    tidy = _RecordingTidy()
    attempts = {"n": 0}

    async def flaky_list_scopes() -> list[str]:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("database is locked")
        return ["global"]

    trigger = NotesTidyTrigger(tidy=tidy, list_scopes=flaky_list_scopes, interval_seconds=0.02)

    task = asyncio.create_task(trigger.run())
    await asyncio.sleep(0.08)
    trigger.stop()
    await asyncio.wait_for(task, timeout=1.0)

    assert attempts["n"] >= 2
    assert tidy.calls  # the sweep after the failure did real work
    assert set(tidy.calls) == {"global"}


async def test_stop_mid_sweep_abandons_the_remaining_scopes() -> None:
    """A sweep over many scopes must not hold up shutdown: once stopped it
    stops visiting, rather than finishing the whole list first."""
    scopes = [f"scope-{i:02d}" for i in range(20)]
    gate = asyncio.Event()

    class _BlockingTidy(_RecordingTidy):
        async def reorg(self, *, scope_name: str) -> Any:
            self.calls.append(scope_name)
            if len(self.calls) == 1:
                await gate.wait()
            return None

    tidy = _BlockingTidy()
    trigger = _trigger(tidy, scopes, interval_seconds=30.0)

    task = asyncio.create_task(trigger.run())
    await asyncio.sleep(0.02)
    assert tidy.calls == ["scope-00"]  # parked inside the first scope

    trigger.stop()
    gate.set()
    await asyncio.wait_for(task, timeout=1.0)

    assert tidy.calls == ["scope-00"]  # the other 19 were abandoned


async def test_shutdown_stops_the_sweep_loop_too() -> None:
    tidy = _RecordingTidy()
    trigger = _trigger(tidy, ["global"], interval_seconds=0.02)

    task = asyncio.create_task(trigger.run())
    await asyncio.sleep(0.01)
    await trigger.shutdown()
    await asyncio.wait_for(task, timeout=1.0)

    before = len(tidy.calls)
    await asyncio.sleep(0.1)
    assert len(tidy.calls) == before  # no further interval passes
