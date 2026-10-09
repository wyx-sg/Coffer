"""The task supervisor: named tasks, crash lines, restart on request, the shutdown sweep."""

from __future__ import annotations

import asyncio
import logging

import pytest

from coffer.application.runtime.supervisor import Restart, TaskSupervisor


def _crash_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage() == "runtime.task.crashed"]


@pytest.mark.acceptance(
    spec="daemon", scenario="a background task that crashes is logged with its name"
)
async def test_a_crash_is_logged_with_the_task_name_and_counted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sup = TaskSupervisor()

    async def boom() -> None:
        raise RuntimeError("the poll loop broke")

    with caplog.at_level(logging.ERROR):
        task = sup.spawn(boom(), name="telegram-poll:family")
        await asyncio.wait({task})
    assert task.get_name() == "telegram-poll:family"
    [record] = _crash_records(caplog)
    assert record.task == "telegram-poll:family"  # type: ignore[attr-defined]
    assert record.error == "RuntimeError"  # type: ignore[attr-defined]
    assert record.exc_info is not None and "the poll loop broke" in str(record.exc_info[1])
    stats = sup.stats()
    assert stats.crashes == 1
    assert stats.last_crash is not None
    assert stats.last_crash.task == "telegram-poll:family"
    # The class name only: the status surface answers without a token.
    assert stats.last_crash.error == "RuntimeError"


async def test_a_task_that_ends_cleanly_or_is_cancelled_is_not_a_crash() -> None:
    sup = TaskSupervisor()

    async def fine() -> int:
        return 7

    async def forever() -> None:
        await asyncio.Event().wait()

    done = sup.spawn(fine(), name="fine")
    assert await done == 7
    waiting = sup.spawn(forever(), name="forever")
    await asyncio.sleep(0)
    waiting.cancel()
    await asyncio.wait({waiting})
    assert sup.stats().crashes == 0
    assert sup.stats().running == 0


@pytest.mark.acceptance(
    spec="daemon", scenario="a crashed channel adapter restarts without touching the others"
)
async def test_a_restarting_task_comes_back_after_a_crash_and_only_it() -> None:
    sup = TaskSupervisor()
    attempts = {"a": 0, "b": 0}
    b_running = asyncio.Event()
    a_back = asyncio.Event()

    async def adapter_a() -> None:
        attempts["a"] += 1
        if attempts["a"] == 1:
            raise ConnectionError("socket reset")
        a_back.set()
        await asyncio.Event().wait()

    async def adapter_b() -> None:
        attempts["b"] += 1
        b_running.set()
        await asyncio.Event().wait()

    fast = Restart(initial=0.01, cap=0.01)
    a = sup.spawn_restarting(adapter_a, name="telegram-poll:a", restart=fast)
    b = sup.spawn_restarting(adapter_b, name="telegram-poll:b", restart=fast)
    await asyncio.wait_for(a_back.wait(), timeout=2)
    await asyncio.wait_for(b_running.wait(), timeout=2)
    assert attempts == {"a": 2, "b": 1}
    assert sup.stats().crashes == 1
    assert sup.stats().last_crash is not None
    assert sup.stats().last_crash.restarting is True
    assert not a.done() and not b.done()
    await sup.shutdown(timeout=1)
    assert a.cancelled() and b.cancelled()


async def test_a_restarting_task_that_returns_is_not_restarted() -> None:
    sup = TaskSupervisor()
    runs = 0

    async def once() -> None:
        nonlocal runs
        runs += 1

    await sup.spawn_restarting(once, name="once", restart=Restart(initial=0.01))
    assert runs == 1


async def test_the_restart_backoff_doubles_to_its_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    sup = TaskSupervisor()
    waits: list[float] = []
    real_sleep = asyncio.sleep
    attempts = 0

    async def record_sleep(delay: float) -> None:
        waits.append(delay)
        await real_sleep(0)

    async def flaky() -> None:
        nonlocal attempts
        attempts += 1
        if attempts <= 4:
            raise ValueError("again")

    monkeypatch.setattr(asyncio, "sleep", record_sleep)
    await sup.spawn_restarting(flaky, name="flaky", restart=Restart(initial=1.0, cap=3.0))
    assert waits == [1.0, 2.0, 3.0, 3.0]


@pytest.mark.acceptance(
    spec="daemon", scenario="shutdown cancels the background tasks still running"
)
async def test_shutdown_cancels_every_task_still_running() -> None:
    sup = TaskSupervisor()

    async def forever() -> None:
        await asyncio.Event().wait()

    first = sup.spawn(forever(), name="probe")
    second = sup.spawn_restarting(forever, name="worker")
    await asyncio.sleep(0)
    assert sup.running_names() == ["probe", "worker"]
    cancelled = await sup.shutdown(timeout=1)
    assert cancelled == ["probe", "worker"]
    assert first.cancelled() and second.cancelled()
    assert sup.stats().running == 0
    assert sup.stats().crashes == 0


async def test_running_tasks_are_counted_by_the_name_before_the_colon() -> None:
    sup = TaskSupervisor()
    gate = asyncio.Event()
    started = [
        sup.spawn(gate.wait(), name="seatalk-ws:family"),
        sup.spawn(gate.wait(), name="seatalk-ws:work"),
        sup.spawn(gate.wait(), name="reconciler"),
    ]
    await asyncio.sleep(0)
    assert sup.running_by_name() == {"reconciler": 1, "seatalk-ws": 2}
    gate.set()
    await asyncio.wait(started)
    assert sup.running_by_name() == {}
