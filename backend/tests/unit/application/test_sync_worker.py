"""Unit tests for the near-real-time auto-sync worker (spec 010, ADR-043).

A fake clock drives the three scheduling signals — debounced local changes,
the remote-head probe, and the fallback sweep — without real sleeps.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from coffer.application.sync.worker import SUPPRESS_GRACE_SECONDS, SyncWorker
from coffer.domain.sync.errors import SyncInProgress
from coffer.domain.sync.models import SyncConfig, SyncState, SyncStatus


class _FakeService:
    def __init__(self) -> None:
        self.runs = 0
        self.is_running = False
        self.outcome_status = SyncStatus.CLEAN
        self.raise_in_progress = False

    async def run(self) -> SyncState:
        if self.raise_in_progress:
            raise SyncInProgress()
        self.runs += 1
        return SyncState(status=self.outcome_status, last_sync_at=None, last_error=None)


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

        self.state = SyncState(status=SyncStatus.CLEAN, last_sync_at=None, last_error=None)

    async def get_config(self) -> SyncConfig:
        return self.config

    async def get_state(self) -> SyncState:
        return self.state


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


async def test_grace_window_drops_post_run_watcher_echo() -> None:
    """The watcher delivers the run's own write batch AFTER lock release; the
    grace window must swallow it (review #283 blocker 1)."""
    service, config, git, clock = _FakeService(), _FakeConfigService(), _FakeGit(), _Clock()
    worker = _worker(service, config, git, clock)
    await worker._maybe_sync()  # startup run; grace starts now
    worker.notify_change()  # the echo, inside the grace window
    clock.now += 60
    await worker._maybe_sync()
    assert service.runs == 1  # echo dropped: no follow-up run
    clock.now += SUPPRESS_GRACE_SECONDS
    worker.notify_change()  # a genuine change after the grace window
    clock.now += 6
    await worker._maybe_sync()
    assert service.runs == 2


async def test_conflicted_state_pauses_auto_runs() -> None:
    """Auto-sync must not blow through a conflict — a rerun would silently
    resolve it local-wins (review #283 blocker 2)."""
    service, config, git, clock = _FakeService(), _FakeConfigService(), _FakeGit(), _Clock()
    config.state = SyncState(status=SyncStatus.CONFLICTED, last_sync_at=None, last_error=None)
    worker = _worker(service, config, git, clock)
    worker.notify_change()
    git.remote_sha = "sha-moved"
    clock.now += 120
    await worker._maybe_sync()
    assert service.runs == 0  # neither change, probe, nor sweep runs
    config.state = SyncState(status=SyncStatus.CLEAN, last_sync_at=None, last_error=None)
    await worker._maybe_sync()
    assert service.runs == 1  # resumes once resolved


async def test_conflicted_outcome_does_not_memoize_head() -> None:
    """A conflicted run stopped before pushing; memoizing its local head would
    make the probe rerun straight back into the conflict."""
    service, config, git, clock = _FakeService(), _FakeConfigService(), _FakeGit(), _Clock()
    worker = _worker(service, config, git, clock)
    await worker._maybe_sync()  # clean startup run memoizes sha-0
    service.outcome_status = SyncStatus.CONFLICTED
    git.local_sha = "sha-local-dirty"
    worker.notify_change()
    clock.now += 6 + SUPPRESS_GRACE_SECONDS
    await worker._maybe_sync()  # conflicted run
    assert worker._last_seen_head == "sha-0"  # unchanged, not the dirty local


async def test_sync_in_progress_requeues_the_change() -> None:
    """A change racing a manual run must not wait for the 300s sweep."""
    service, config, git, clock = _FakeService(), _FakeConfigService(), _FakeGit(), _Clock()
    worker = _worker(service, config, git, clock)
    await worker._maybe_sync()  # startup
    clock.now += SUPPRESS_GRACE_SECONDS + 1  # leave the startup grace window
    service.raise_in_progress = True
    worker.notify_change()
    clock.now += 6
    await worker._maybe_sync()  # manual run holds the lock: requeued
    assert service.runs == 1
    service.raise_in_progress = False
    clock.now += 6 + SUPPRESS_GRACE_SECONDS
    await worker._maybe_sync()
    assert service.runs == 2  # the queued change fires once the lock frees
