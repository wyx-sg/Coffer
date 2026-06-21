"""Unit tests for the auto-distill catch-up sweep + worker (007 FR-046).

Drives ``AutoDistillSweep.run_once`` and ``AutoDistillSweepWorker`` against pure
fakes — no real LLM, no real DB. Eligibility, capping, idempotency, failure
suppression, and the no-model no-op are all exercised here.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from coffer.application.distill.auto_distill import (
    AutoDistillSweep,
    AutoDistillSweepWorker,
)
from coffer.application.distill.service import NoModelConfiguredError
from coffer.domain.distill.session import TranscriptSession

NOW = datetime(2026, 6, 22, 12, 0, 0, tzinfo=UTC)
SETTLE = 900.0  # 15 min
RECENCY = 604800.0  # 7 days


def _session(session_id: str, *, age_seconds: float, path: str | None = None) -> TranscriptSession:
    return TranscriptSession(
        session_id=session_id,
        agent_type_value="claude_code",
        project_path="/repo",
        started_at=None,
        last_activity_at=NOW - timedelta(seconds=age_seconds),
        source_path=path if path is not None else f"/transcripts/{session_id}.jsonl",
    )


class _Recorder:
    """Collects distill + mark calls and acts as the ledger fake."""

    def __init__(self) -> None:
        self.distilled: list[tuple[str, str]] = []
        self.marked: list[tuple[str, str, str]] = []
        self._ledger: set[tuple[str, str, str]] = set()
        self.distill_error: Exception | None = None

    async def distill(self, name: str, session_id: str) -> None:
        if self.distill_error is not None:
            raise self.distill_error
        self.distilled.append((name, session_id))

    async def is_distilled(self, name: str, session_id: str, sha: str) -> bool:
        return (name, session_id, sha) in self._ledger

    async def mark_distilled(self, name: str, session_id: str, sha: str) -> None:
        self.marked.append((name, session_id, sha))
        self._ledger.add((name, session_id, sha))

    def seed(self, name: str, session_id: str, sha: str) -> None:
        self._ledger.add((name, session_id, sha))


def _build_sweep(
    rec: _Recorder,
    *,
    agents: dict[str, list[TranscriptSession]],
    raising_agents: set[str] | None = None,
    max_per_sweep: int = 20,
    session_sha=lambda path: f"sha-of-{path}",
    distill=None,
) -> AutoDistillSweep:
    raising = raising_agents or set()

    async def list_agent_names() -> list[str]:
        return list(agents)

    async def list_sessions(name: str) -> list[TranscriptSession]:
        if name in raising:
            raise RuntimeError("unsupported agent type")
        return agents[name]

    return AutoDistillSweep(
        list_agent_names=list_agent_names,
        list_sessions=list_sessions,
        distill=distill if distill is not None else rec.distill,
        is_distilled=rec.is_distilled,
        mark_distilled=rec.mark_distilled,
        session_sha=session_sha,
        now=lambda: NOW,
        settle_seconds=SETTLE,
        recency_seconds=RECENCY,
        max_per_sweep=max_per_sweep,
    )


async def test_eligible_session_is_distilled_and_marked():
    rec = _Recorder()
    sweep = _build_sweep(rec, agents={"a1": [_session("s1", age_seconds=3600)]})
    await sweep.run_once()
    assert rec.distilled == [("a1", "s1")]
    assert rec.marked == [("a1", "s1", "sha-of-/transcripts/s1.jsonl")]


async def test_in_progress_session_too_recent_is_skipped():
    rec = _Recorder()
    # age below the settle threshold → still in progress.
    sweep = _build_sweep(rec, agents={"a1": [_session("s1", age_seconds=SETTLE - 1)]})
    await sweep.run_once()
    assert rec.distilled == []
    assert rec.marked == []


async def test_too_old_session_beyond_recency_is_skipped():
    rec = _Recorder()
    sweep = _build_sweep(rec, agents={"a1": [_session("s1", age_seconds=RECENCY + 1)]})
    await sweep.run_once()
    assert rec.distilled == []


async def test_already_distilled_session_is_skipped():
    rec = _Recorder()
    rec.seed("a1", "s1", "sha-of-/transcripts/s1.jsonl")
    sweep = _build_sweep(rec, agents={"a1": [_session("s1", age_seconds=3600)]})
    await sweep.run_once()
    assert rec.distilled == []  # is_distilled True → never distilled
    assert rec.marked == []


async def test_session_with_no_last_activity_is_skipped():
    rec = _Recorder()
    s = TranscriptSession(
        session_id="s1",
        agent_type_value="claude_code",
        project_path="/repo",
        started_at=None,
        last_activity_at=None,
        source_path="/transcripts/s1.jsonl",
    )
    sweep = _build_sweep(rec, agents={"a1": [s]})
    await sweep.run_once()
    assert rec.distilled == []


async def test_over_cap_only_distills_cap_and_logs_deferral(caplog):
    rec = _Recorder()
    sessions = [_session(f"s{i}", age_seconds=3600 + i) for i in range(5)]
    sweep = _build_sweep(rec, agents={"a1": sessions}, max_per_sweep=2)
    with caplog.at_level("INFO"):
        await sweep.run_once()
    assert len(rec.distilled) == 2
    assert len(rec.marked) == 2
    assert any("auto_distill.deferred" in r.message for r in caplog.records)


async def test_oldest_sessions_are_chosen_first():
    rec = _Recorder()
    # s_new is younger (smaller age), s_old is older (larger age).
    sessions = [_session("s_new", age_seconds=1000), _session("s_old", age_seconds=5000)]
    sweep = _build_sweep(rec, agents={"a1": sessions}, max_per_sweep=1)
    await sweep.run_once()
    assert rec.distilled == [("a1", "s_old")]  # oldest-first


async def test_per_session_distill_failure_is_suppressed_and_not_marked():
    rec = _Recorder()
    calls: list[str] = []

    async def flaky_distill(name: str, session_id: str) -> None:
        calls.append(session_id)
        if session_id == "s1":
            raise RuntimeError("LLM blew up")
        rec.distilled.append((name, session_id))

    sweep = _build_sweep(
        rec,
        agents={"a1": [_session("s1", age_seconds=3600), _session("s2", age_seconds=3601)]},
        distill=flaky_distill,
    )
    await sweep.run_once()
    # Both attempted; s1 failed (unmarked → retried next pass), s2 succeeded.
    assert set(calls) == {"s1", "s2"}
    assert rec.distilled == [("a1", "s2")]
    assert ("a1", "s1", "sha-of-/transcripts/s1.jsonl") not in rec.marked
    assert ("a1", "s2", "sha-of-/transcripts/s2.jsonl") in rec.marked


async def test_no_model_configured_is_a_clean_noop():
    rec = _Recorder()

    async def no_model_distill(name: str, session_id: str) -> None:
        raise NoModelConfiguredError("no internal connection")

    sweep = _build_sweep(
        rec,
        agents={"a1": [_session("s1", age_seconds=3600), _session("s2", age_seconds=3601)]},
        distill=no_model_distill,
    )
    await sweep.run_once()
    assert rec.marked == []  # whole pass no-ops, nothing marked


async def test_agent_whose_list_sessions_raises_is_skipped_others_swept():
    rec = _Recorder()
    sweep = _build_sweep(
        rec,
        agents={
            "bad": [_session("x", age_seconds=3600)],
            "good": [_session("s1", age_seconds=3600)],
        },
        raising_agents={"bad"},
    )
    await sweep.run_once()
    assert rec.distilled == [("good", "s1")]


async def test_session_sha_error_skips_only_that_session():
    rec = _Recorder()

    def sha(path: str) -> str:
        if path.endswith("s1.jsonl"):
            raise OSError("file vanished")
        return f"sha-of-{path}"

    sweep = _build_sweep(
        rec,
        agents={"a1": [_session("s1", age_seconds=3600), _session("s2", age_seconds=3601)]},
        session_sha=sha,
    )
    await sweep.run_once()
    assert rec.distilled == [("a1", "s2")]


async def test_run_once_never_raises_even_if_list_agents_raises():
    rec = _Recorder()

    async def boom() -> list[str]:
        raise RuntimeError("registry down")

    sweep = AutoDistillSweep(
        list_agent_names=boom,
        list_sessions=lambda name: _noop_sessions(),
        distill=rec.distill,
        is_distilled=rec.is_distilled,
        mark_distilled=rec.mark_distilled,
        session_sha=lambda p: "x",
        now=lambda: NOW,
        settle_seconds=SETTLE,
        recency_seconds=RECENCY,
        max_per_sweep=20,
    )
    await sweep.run_once()  # must not raise
    assert rec.distilled == []


async def _noop_sessions() -> list[TranscriptSession]:
    return []


# --------------------------------------------------------------------------
# Worker
# --------------------------------------------------------------------------


async def test_worker_runs_sweep_then_stops_cleanly():
    calls = 0
    started = asyncio.Event()

    async def sweep() -> None:
        nonlocal calls
        calls += 1
        started.set()

    worker = AutoDistillSweepWorker(sweep=sweep, interval_seconds=0.01)
    task = asyncio.create_task(worker.run())
    await asyncio.wait_for(started.wait(), timeout=1.0)
    worker.stop()
    await asyncio.wait_for(task, timeout=1.0)
    assert task.done()
    assert calls >= 1


async def test_worker_sweep_failure_does_not_kill_worker():
    calls = 0
    started = asyncio.Event()

    async def flaky_sweep() -> None:
        nonlocal calls
        calls += 1
        started.set()
        raise RuntimeError("sweep blew up")

    worker = AutoDistillSweepWorker(sweep=flaky_sweep, interval_seconds=0.01)
    task = asyncio.create_task(worker.run())
    await asyncio.wait_for(started.wait(), timeout=1.0)
    worker.stop()
    await asyncio.wait_for(task, timeout=1.0)
    assert task.done()
    assert not task.cancelled()
    assert calls >= 1
