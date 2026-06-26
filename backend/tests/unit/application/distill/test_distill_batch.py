"""Unit tests for DistillBatchService — enqueue logic, skip-unchanged, status."""

from __future__ import annotations

import pytest

from coffer.application.async_ops.registry import AsyncOpRegistry, OpState
from coffer.application.async_ops.runner import AsyncOpRunner
from coffer.application.distill.batch import (
    STATUS_DONE,
    STATUS_NEVER,
    STATUS_STALE,
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


def _sha(path: str) -> str:
    """The fake content hash — deterministic in the transcript path."""
    return f"sha-of-{path}"


class _Fixture:
    """A DistillBatchService wired against in-memory fakes.

    ``already_distilled`` sessions sit in the ledger at their CURRENT content
    sha (→ ``done``). ``stale`` sessions sit in the ledger at an OLDER sha that
    no longer matches the current transcript (→ ``stale``).
    """

    def __init__(
        self,
        *,
        sessions: list[str],
        already_distilled: set[str] = frozenset(),  # type: ignore[assignment]
        stale: set[str] = frozenset(),  # type: ignore[assignment]
    ) -> None:
        self.registry = AsyncOpRegistry()
        self.runner = AsyncOpRunner(self.registry, concurrency=1)  # not started: enqueue-only
        self._sessions = [_session(s) for s in sessions]
        self.sessions_by_id = {s.session_id: s for s in self._sessions}
        # ledger: session_id -> set of content shas it has been distilled at.
        self._ledger: dict[str, set[str]] = {}
        for s in self._sessions:
            if s.session_id in already_distilled:
                self._ledger.setdefault(s.session_id, set()).add(_sha(s.source_path))
            if s.session_id in stale:
                self._ledger.setdefault(s.session_id, set()).add(f"old-sha-{s.session_id}")
        self.distilled_calls: list[str] = []
        self.marked: list[tuple[str, str, str]] = []

        async def list_sessions(
            agent: str, *, limit: int, **_kw: object
        ) -> list[TranscriptSession]:
            return self._sessions

        async def distilled_shas(_agent: str) -> dict[str, set[str]]:
            return {sid: set(shas) for sid, shas in self._ledger.items()}

        async def distill(_agent: str, session_id: str) -> None:
            self.distilled_calls.append(session_id)

        async def is_distilled(_agent: str, session_id: str, sha: str) -> bool:
            return sha in self._ledger.get(session_id, set())

        async def mark_distilled(agent: str, session_id: str, sha: str) -> None:
            self.marked.append((agent, session_id, sha))

        self.svc = DistillBatchService(
            runner=self.runner,
            registry=self.registry,
            list_sessions=list_sessions,
            distilled_shas=distilled_shas,
            distill=distill,
            is_distilled=is_distilled,
            mark_distilled=mark_distilled,
            session_sha=_sha,
        )

    def sessions(self, *ids: str) -> list[TranscriptSession]:
        return [self.sessions_by_id[i] for i in ids]


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


async def test_stale_session_is_re_enqueued():
    """A session distilled at an OLDER sha is not skipped — it re-distills."""
    fx = _Fixture(sessions=["a"], stale={"a"})
    result = await fx.svc.enqueue_sessions("agent1", ["a"])
    assert result.queued == 1  # current sha not in ledger → re-enqueued
    assert result.skipped == 0


async def test_derived_statuses_done_vs_never():
    fx = _Fixture(sessions=["a", "b"], already_distilled={"a"})
    statuses = await fx.svc.derived_statuses("agent1", fx.sessions("a", "b"))
    assert statuses == {"a": STATUS_DONE, "b": STATUS_NEVER}


async def test_derived_statuses_stale_when_content_changed():
    """Distilled at an older content sha, then the transcript grew → stale."""
    fx = _Fixture(sessions=["a", "b", "c"], already_distilled={"a"}, stale={"b"})
    statuses = await fx.svc.derived_statuses("agent1", fx.sessions("a", "b", "c"))
    assert statuses == {"a": STATUS_DONE, "b": STATUS_STALE, "c": STATUS_NEVER}


async def test_inflight_maps_session_id():
    fx = _Fixture(sessions=["a", "b"], already_distilled=set())
    await fx.svc.enqueue_all("agent1")
    inflight = fx.svc.inflight("agent1")
    assert set(inflight) == {"a", "b"}
    assert inflight["a"].state is OpState.queued
