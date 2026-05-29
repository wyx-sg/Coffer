import asyncio

import pytest

from coffer.application.retention_worker import RetentionWorker


class _FakeService:
    """Stand-in for RetentionService — just records prune() invocations."""

    def __init__(self, *, raise_on_call: int | None = None) -> None:
        self.calls = 0
        self._raise_on_call = raise_on_call
        self.last_result: dict[str, int] | None = None

    async def prune(self) -> dict[str, int]:
        self.calls += 1
        if self._raise_on_call is not None and self.calls == self._raise_on_call:
            raise RuntimeError("transient prune failure")
        self.last_result = {"audit_log": self.calls}
        return self.last_result


@pytest.mark.asyncio
async def test_worker_runs_prune_on_start():
    """The worker prunes immediately on start (catch-up)."""
    svc = _FakeService()
    worker = RetentionWorker(service=svc, interval_seconds=3600)  # type: ignore[arg-type]
    task = asyncio.create_task(worker.run())
    # Yield until the first prune lands
    for _ in range(50):
        await asyncio.sleep(0.005)
        if svc.calls >= 1:
            break
    worker.stop()
    await asyncio.wait_for(task, timeout=1.0)
    assert svc.calls == 1


@pytest.mark.asyncio
async def test_worker_polls_at_interval():
    """After the initial run, the worker waits `interval_seconds` between runs.

    Event-driven (TEST-001): instead of `asyncio.sleep(0.5)` + `>= 5`, we poll
    `svc.calls` under a hard wall-clock cap so the test does not flake on a
    loaded CI box (and finishes immediately on a fast one).
    """
    svc = _FakeService()
    worker = RetentionWorker(service=svc, interval_seconds=0.05)  # type: ignore[arg-type]
    task = asyncio.create_task(worker.run())
    target = 3
    deadline = asyncio.get_event_loop().time() + 5.0
    while svc.calls < target and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.01)
    worker.stop()
    await asyncio.wait_for(task, timeout=2.0)
    assert svc.calls >= target, f"expected >= {target} prune calls, got {svc.calls}"


@pytest.mark.asyncio
async def test_worker_survives_prune_exception():
    """A raised exception in prune() does not kill the worker.

    Event-driven (TEST-001): wait until at least 2 prune calls land, capped
    by a 5 s deadline.  Avoids the fixed `asyncio.sleep(0.3)` that flakes on
    slow CI.
    """
    svc = _FakeService(raise_on_call=1)
    worker = RetentionWorker(service=svc, interval_seconds=0.05)  # type: ignore[arg-type]
    task = asyncio.create_task(worker.run())
    target = 2
    deadline = asyncio.get_event_loop().time() + 5.0
    while svc.calls < target and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.01)
    worker.stop()
    await asyncio.wait_for(task, timeout=2.0)
    # First call raised; subsequent calls still happened
    assert svc.calls >= target, f"expected >= {target} prune calls, got {svc.calls}"


@pytest.mark.asyncio
async def test_worker_stops_cleanly():
    """stop() ends the run loop without raising."""
    svc = _FakeService()
    worker = RetentionWorker(service=svc, interval_seconds=10.0)  # type: ignore[arg-type]
    task = asyncio.create_task(worker.run())
    await asyncio.sleep(0.05)
    worker.stop()
    await asyncio.wait_for(task, timeout=1.0)
    assert task.done()
    # Task completed without exception
    assert task.exception() is None
