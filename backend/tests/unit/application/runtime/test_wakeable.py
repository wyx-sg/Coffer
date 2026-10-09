"""The shared worker loop: pokes, the fallback, settling, demand, and what it
reports (ADR background-workers-wake-on-events)."""

from __future__ import annotations

import asyncio
import contextlib
import logging

import pytest

from coffer.application.runtime.wakeable import WakeableLoop
from coffer.application.runtime.workers import WorkerMode, WorkerRegistry


class Runs:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[bool] = []
        self.fail = fail
        self.ran = asyncio.Event()

    async def __call__(self, poked: bool) -> None:
        self.calls.append(poked)
        self.ran.set()
        if self.fail:
            raise RuntimeError("boom")


@contextlib.asynccontextmanager
async def serving(loop: WakeableLoop):  # type: ignore[no-untyped-def]
    task = asyncio.create_task(loop.serve())
    await asyncio.sleep(0)
    try:
        yield task
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def _until(predicate, timeout: float = 2.0) -> None:  # type: ignore[no-untyped-def]
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.005)


async def test_a_poke_runs_it_once_and_a_burst_is_one_run() -> None:
    runs, reg = Runs(), WorkerRegistry()
    loop = WakeableLoop("w", runs, fallback=None, settle=0.05, registry=reg)
    async with serving(loop):
        loop.poke()
        loop.poke()
        await asyncio.sleep(0.01)
        loop.poke()
        await _until(lambda: runs.calls)
        await asyncio.sleep(0.1)
    assert runs.calls == [True]


async def test_with_no_fallback_it_never_runs_unpoked() -> None:
    runs = Runs()
    loop = WakeableLoop("w", runs, fallback=None, registry=WorkerRegistry())
    async with serving(loop):
        await asyncio.sleep(0.1)
    assert runs.calls == []


async def test_the_fallback_runs_it_unpoked() -> None:
    runs = Runs()
    loop = WakeableLoop("w", runs, fallback=0.02, registry=WorkerRegistry())
    async with serving(loop):
        await _until(lambda: len(runs.calls) >= 2)
    assert runs.calls[:2] == [False, False]


async def test_a_poke_during_a_run_runs_it_again() -> None:
    gate = asyncio.Event()
    calls: list[bool] = []

    async def run(poked: bool) -> None:
        calls.append(poked)
        if len(calls) == 1:
            await gate.wait()

    loop = WakeableLoop("w", run, fallback=None, registry=WorkerRegistry())
    async with serving(loop):
        loop.poke()
        await _until(lambda: calls)
        loop.poke()
        gate.set()
        await _until(lambda: len(calls) == 2)


async def test_a_failed_run_is_logged_counted_and_the_loop_carries_on(
    caplog: pytest.LogCaptureFixture,
) -> None:
    runs, reg = Runs(fail=True), WorkerRegistry()
    loop = WakeableLoop("w", runs, fallback=None, failure_event="x.failed", registry=reg)
    with caplog.at_level(logging.ERROR):
        async with serving(loop):
            loop.poke()
            await _until(lambda: reg.snapshot()[0].runs == 1)
            loop.poke()
            await _until(lambda: reg.snapshot()[0].runs == 2)
            (record,) = reg.snapshot()
    assert record.failures == 2
    assert record.last_ok is False
    assert "x.failed" in caplog.messages


async def test_without_demand_it_parks_and_the_fallback_does_not_fire() -> None:
    runs, reg = Runs(), WorkerRegistry()
    loop = WakeableLoop("w", runs, fallback=0.02, mode=WorkerMode.ON_DEMAND, registry=reg)
    loop.set_demand(False)
    async with serving(loop):
        await _until(lambda: reg.snapshot() and reg.snapshot()[0].state == "parked")
        await asyncio.sleep(0.1)
        assert runs.calls == []
        assert reg.snapshot()[0].next_run_at is None
        loop.set_demand(True)
        await _until(lambda: runs.calls)
        loop.set_demand(False)
        await _until(lambda: reg.snapshot()[0].state == "parked")
    assert reg.snapshot() == []


async def test_it_reports_its_schedule_and_last_run() -> None:
    runs, reg = Runs(), WorkerRegistry()
    loop = WakeableLoop("w", runs, fallback=60.0, registry=reg)
    async with serving(loop):
        await _until(lambda: reg.snapshot() != [])
        (waiting,) = reg.snapshot()
        assert waiting.mode is WorkerMode.EVENT_FALLBACK
        assert waiting.state == "waiting"
        assert waiting.next_run_at is not None
        assert waiting.runs == 0 and waiting.last_ok is None
        loop.poke()
        await _until(lambda: reg.snapshot()[0].runs == 1)
        (done,) = reg.snapshot()
    assert done.last_ok is True
    assert done.last_duration_ms is not None
    assert done.last_started_at is not None
    assert reg.snapshot() == [], "a stopped worker is no longer listed"


def test_a_stopped_worker_does_not_drop_a_newer_one_of_the_same_name() -> None:
    reg = WorkerRegistry()
    old = reg.register("w", WorkerMode.EVENT)
    new = reg.register("w", WorkerMode.EVENT)
    reg.finished("w", old, ok=False, seconds=1.0)
    reg.drop("w", old)
    (record,) = reg.snapshot()
    assert record.runs == 0
    reg.drop("w", new)
    assert reg.snapshot() == []
