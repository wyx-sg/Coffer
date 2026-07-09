"""Unit tests for the near-real-time auto-sync worker (spec 010, ADR-043).

A fake clock drives the three scheduling signals — debounced local changes,
the remote-head probe, and the fallback sweep — without real sleeps.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from coffer.application.sync.worker import SyncWorker
from coffer.domain.sync.models import SyncConfig


class _FakeService:
    def __init__(self) -> None:
        self.runs = 0
        self.is_running = False

    async def run(self) -> None:
        self.runs += 1


class _FakeConfigService:
    def __init__(self, *, auto: bool = True, interval: int = 3600, poll: int = 5) -> None:
        self.config = SyncConfig(
            remote="git@example:vault.git",
            enabled=True,
            auto=auto,
            interval_seconds=interval,
            branch="main",
            updated_at=datetime.now(tz=UTC),
            poll_remote_seconds=poll,
        )

    async def get_config(self) -> SyncConfig:
        return self.config


class _FakeGit:
    def __init__(self) -> None:
        self.remote_sha: str | None = "sha-0"
        self.local_sha: str | None = "sha-0"

    def remote_head(self, remote: str, branch: str) -> str | None:
        return self.remote_sha

    def head(self) -> str | None:
        return self.local_sha


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _worker(service: Any, config: Any, git: Any, clock: _Clock, **kw: Any) -> SyncWorker:
    return SyncWorker(service, config, git, clock=clock, **kw)


async def test_startup_converges_via_fallback_then_idles() -> None:
    service, config, git, clock = _FakeService(), _FakeConfigService(), _FakeGit(), _Clock()
    worker = _worker(service, config, git, clock)
    await worker._maybe_sync()
    assert service.runs == 1  # last_run None -> immediate fallback sweep
    clock.now += 10
    await worker._maybe_sync()
    assert service.runs == 1  # nothing changed: no second run


async def test_change_fires_after_quiet_period_only() -> None:
    service, config, git, clock = _FakeService(), _FakeConfigService(), _FakeGit(), _Clock()
    worker = _worker(service, config, git, clock)
    await worker._maybe_sync()  # startup sweep
    worker.notify_change()
    clock.now += 2
    worker.notify_change()  # keeps the debounce window open
    clock.now += 3
    await worker._maybe_sync()
    assert service.runs == 1  # only 3s quiet since last change
    clock.now += 2.5
    await worker._maybe_sync()
    assert service.runs == 2  # 5s quiet -> due


async def test_change_stream_capped() -> None:
    service, config, git, clock = _FakeService(), _FakeConfigService(), _FakeGit(), _Clock()
    worker = _worker(service, config, git, clock)
    await worker._maybe_sync()
    for _ in range(10):
        worker.notify_change()
        clock.now += 4  # never 5s quiet, but the cap (30s) passes
        await worker._maybe_sync()
        if service.runs > 1:
            break
    assert service.runs == 2


async def test_remote_head_movement_triggers_run() -> None:
    service, config, git, clock = _FakeService(), _FakeConfigService(), _FakeGit(), _Clock()
    worker = _worker(service, config, git, clock)
    await worker._maybe_sync()  # startup sweep; probe records sha-0
    clock.now += 6
    await worker._maybe_sync()
    assert service.runs == 1  # head unchanged
    git.remote_sha = "sha-1"
    clock.now += 6
    await worker._maybe_sync()
    assert service.runs == 2  # head moved -> run


async def test_own_push_does_not_retrigger() -> None:
    service, config, git, clock = _FakeService(), _FakeConfigService(), _FakeGit(), _Clock()
    worker = _worker(service, config, git, clock)
    await worker._maybe_sync()
    # Our run pushed sha-9; git.head() reports it and the probe must not fire.
    git.remote_sha = git.local_sha = "sha-9"
    worker.notify_change()
    clock.now += 6
    await worker._maybe_sync()  # change-due run; afterwards last_seen = sha-9
    runs = service.runs
    clock.now += 6
    await worker._maybe_sync()
    assert service.runs == runs  # probe sees our own sha: no extra run


async def test_notifications_suppressed_while_running() -> None:
    service, config, git, clock = _FakeService(), _FakeConfigService(), _FakeGit(), _Clock()
    worker = _worker(service, config, git, clock)
    service.is_running = True
    worker.notify_change()
    service.is_running = False
    clock.now += 10
    await worker._maybe_sync()  # startup sweep runs regardless
    runs = service.runs
    clock.now += 10
    await worker._maybe_sync()
    assert service.runs == runs  # the suppressed change never queued a run


async def test_auto_off_clears_pending_changes() -> None:
    service, git, clock = _FakeService(), _FakeGit(), _Clock()
    config = _FakeConfigService(auto=False)
    worker = _worker(service, config, git, clock)
    worker.notify_change()
    clock.now += 60
    await worker._maybe_sync()
    assert service.runs == 0
    config.config.auto = True
    await worker._maybe_sync()  # startup sweep only — old change was cleared
    assert service.runs == 1


async def test_probe_respects_cadence() -> None:
    service, config, git, clock = _FakeService(), _FakeConfigService(), _FakeGit(), _Clock()
    worker = _worker(service, config, git, clock)
    await worker._maybe_sync()
    git.remote_sha = "sha-1"
    clock.now += 2  # below poll_remote_seconds=5: probe must not fire yet
    await worker._maybe_sync()
    assert service.runs == 1
    clock.now += 4
    await worker._maybe_sync()
    assert service.runs == 2
