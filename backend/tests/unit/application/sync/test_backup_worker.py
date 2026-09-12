"""The backup timer (spec vault-export-import ``## Backup``)."""

from __future__ import annotations

import asyncio

import pytest

from coffer.application.sync import backup_worker
from coffer.application.sync.backup_worker import BackupWorker
from coffer.domain.sync.backup import (
    DEFAULT_INTERVAL_SECONDS,
    BackupRemote,
    BackupRun,
    BackupRunStatus,
)

_REAL_WAIT_FOR = asyncio.wait_for


class _FakeService:
    """Stand-in for BackupService — records run_once() invocations."""

    def __init__(
        self,
        *,
        remote: BackupRemote | None = None,
        raise_on_call: int | None = None,
    ) -> None:
        self.calls = 0
        self.remote = remote
        self._raise_on_call = raise_on_call

    async def get(self) -> BackupRemote | None:
        return self.remote

    async def run_once(self) -> BackupRun:
        self.calls += 1
        if self._raise_on_call is not None and self.calls == self._raise_on_call:
            raise RuntimeError("transient backup failure")
        return BackupRun(status=BackupRunStatus.OK, commit=f"abc{self.calls}")


def _record_intervals(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Collapse the worker's sleep to ~nothing, keeping the interval it asked for.

    The worker's cadence is measured in hours, so the only way to assert it
    without waiting is to watch the timeout it requests rather than the time it
    actually spends waiting.
    """
    seen: list[float] = []

    async def _spy(awaitable, timeout=None):  # type: ignore[no-untyped-def]
        seen.append(timeout)
        return await _REAL_WAIT_FOR(awaitable, timeout=0.001)

    monkeypatch.setattr(backup_worker.asyncio, "wait_for", _spy)
    return seen


async def _wait_for_calls(svc: _FakeService, target: int) -> None:
    """Poll until `target` runs land, capped by a wall-clock deadline (TEST-001)."""
    deadline = asyncio.get_event_loop().time() + 5.0
    while svc.calls < target and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_worker_backs_up_on_start() -> None:
    """The worker backs up immediately on start (catch-up)."""
    svc = _FakeService()
    worker = BackupWorker(svc, interval_seconds=3600)
    task = asyncio.create_task(worker.run())
    await _wait_for_calls(svc, 1)
    worker.stop()
    await asyncio.wait_for(task, timeout=1.0)
    assert svc.calls == 1


@pytest.mark.asyncio
async def test_worker_survives_a_failed_run() -> None:
    """A raised exception inside a run does not kill the worker.

    This is the property the whole worker exists to hold: an unreachable remote
    costs one run, not every run after it.
    """
    svc = _FakeService(raise_on_call=1)
    worker = BackupWorker(svc, interval_seconds=0.05)
    task = asyncio.create_task(worker.run())
    await _wait_for_calls(svc, 2)
    worker.stop()
    await asyncio.wait_for(task, timeout=2.0)
    assert svc.calls >= 2, f"expected >= 2 backup runs, got {svc.calls}"
    assert task.exception() is None


@pytest.mark.asyncio
async def test_stop_ends_the_loop_promptly() -> None:
    """stop() ends the run loop without waiting out the interval."""
    svc = _FakeService()
    worker = BackupWorker(svc, interval_seconds=3600)
    task = asyncio.create_task(worker.run())
    await _wait_for_calls(svc, 1)
    worker.stop()
    await asyncio.wait_for(task, timeout=1.0)
    assert task.done()
    assert task.exception() is None


@pytest.mark.asyncio
async def test_interval_falls_back_to_the_default_without_a_remote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No remote configured still ticks, on the default cadence."""
    seen = _record_intervals(monkeypatch)
    svc = _FakeService(remote=None)
    worker = BackupWorker(svc)
    task = asyncio.create_task(worker.run())
    await _wait_for_calls(svc, 1)
    worker.stop()
    await _REAL_WAIT_FOR(task, timeout=1.0)
    assert seen
    assert seen[0] == float(DEFAULT_INTERVAL_SECONDS)


@pytest.mark.asyncio
async def test_interval_is_reread_between_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Changing the interval in the UI takes effect without a daemon restart."""
    seen = _record_intervals(monkeypatch)
    svc = _FakeService(
        remote=BackupRemote(url="https://example.invalid/vault.git", interval_seconds=111)
    )
    worker = BackupWorker(svc)
    task = asyncio.create_task(worker.run())
    await _wait_for_calls(svc, 1)
    svc.remote = BackupRemote(url="https://example.invalid/vault.git", interval_seconds=222)
    deadline = asyncio.get_event_loop().time() + 5.0
    while 222.0 not in seen and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.01)
    worker.stop()
    await _REAL_WAIT_FOR(task, timeout=1.0)
    assert seen[0] == 111.0
    assert 222.0 in seen
