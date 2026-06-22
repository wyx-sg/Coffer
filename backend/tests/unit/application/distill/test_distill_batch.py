"""Unit tests for DistillBatchService — enqueue logic, skip-unchanged, status."""

from __future__ import annotations

import pytest

from coffer.application.async_ops.registry import AsyncOpRegistry, OpState
from coffer.application.async_ops.runner import AsyncOpRunner
from coffer.application.distill.batch import (
    STATUS_DONE,
    STATUS_NEVER,
    DistillBatchService,
)
from coffer.domain.distill.session import TranscriptSession

pytestmark = pytest.mark.asyncio


def _session(session_id: str) -> TranscriptSession:
    return TranscriptSession(
        session_id=session_id,
        agent_type_value="claude_code",
        project_path="/tmp/proj",
        started_at=None,
        source_path=f"/tmp/{session_id}.jsonl",
    )


class _Fixture:
    """A DistillBatchService wired against in-memory fakes."""

    def __init__(self, *, sessions: list[str], already_distilled: set[str]) -> None:
        self.registry = AsyncOpRegistry()
        self.runner = AsyncOpRunner(self.registry, concurrency=1)  # not started: enqueue-only
        self._sessions = [_session(s) for s in sessions]
        self._distilled = set(already_distilled)
        self.distilled_calls: list[str] = []
        self.marked: list[tuple[str, str, str]] = []

        async def list_sessions(
            agent: str, *, limit: int, **_kw: object
        ) -> list[TranscriptSession]:
            return self._sessions

        async def distilled_ids(_agent: str) -> set[str]:
            return set(self._distilled)

        async def distill(_agent: str, session_id: str) -> None:
            self.distilled_calls.append(session_id)

        async def is_distilled(_agent: str, session_id: str, _sha: str) -> bool:
            return session_id in self._distilled

        async def mark_distilled(agent: str, session_id: str, sha: str) -> None:
            self.marked.append((agent, session_id, sha))

        def session_sha(path: str) -> str:
            return f"sha-of-{path}"

        self.svc = DistillBatchService(
            runner=self.runner,
            registry=self.registry,
            list_sessions=list_sessions,
            distilled_ids=distilled_ids,
            distill=distill,
            is_distilled=is_distilled,
            mark_distilled=mark_distilled,
            session_sha=session_sha,
        )


async def test_enqueue_sessions_skips_already_distilled():
    fx = _Fixture(sessions=["a", "b", "c"], already_distilled={"b"})
    result = await fx.svc.enqueue_sessions("agent1", ["a", "b"])
    assert result.queued == 1  # a
    assert result.skipped == 1  # b
    assert fx.registry.get("distill", "agent1\x00a").state is OpState.queued  # type: ignore[union-attr]
    assert fx.registry.get("distill", "agent1\x00b") is None


async def test_enqueue_all_enqueues_every_undistilled():
    fx = _Fixture(sessions=["a", "b", "c"], already_distilled={"a"})
    result = await fx.svc.enqueue_all("agent1")
    assert result.queued == 2  # b, c
    assert result.skipped == 1  # a
    assert result.total == 3


async def test_enqueue_does_not_double_enqueue_in_flight():
    fx = _Fixture(sessions=["a"], already_distilled=set())
    first = await fx.svc.enqueue_sessions("agent1", ["a"])
    second = await fx.svc.enqueue_sessions("agent1", ["a"])
    assert first.queued == 1
    assert second.queued == 0  # already queued — not re-enqueued


async def test_derived_statuses_done_vs_never():
    fx = _Fixture(sessions=["a", "b"], already_distilled={"a"})
    statuses = await fx.svc.derived_statuses("agent1", ["a", "b"])
    assert statuses == {"a": STATUS_DONE, "b": STATUS_NEVER}


async def test_inflight_maps_session_id():
    fx = _Fixture(sessions=["a", "b"], already_distilled=set())
    await fx.svc.enqueue_all("agent1")
    inflight = fx.svc.inflight("agent1")
    assert set(inflight) == {"a", "b"}
    assert inflight["a"].state is OpState.queued
