"""Integration tests for the async batch-distill routes + status overlay.

Builds a minimal app with the distill router and a fake batch service injected
via dependency_overrides (no DB, no runner).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from coffer.application.async_ops.registry import InflightEntry, OpState
from coffer.application.distill.batch import EnqueueResult
from coffer.domain.distill.session import TranscriptSession
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.distill.routes import router as distill_router
from coffer.surfaces.http.distill.state import (
    get_distill_batch_service,
    get_distill_batch_service_optional,
    get_distill_service,
)

_HEADERS = {"X-Coffer-Token": "t"}

_SESSION = TranscriptSession(
    session_id="sess-001",
    agent_type_value="claude_code",
    project_path="/home/user/repo",
    started_at=datetime(2026, 6, 1, tzinfo=UTC),
    source_path="/home/user/.claude/x.jsonl",
    title="A session",
    last_activity_at=datetime(2026, 6, 1, tzinfo=UTC),
)


class _FakeListService:
    async def list_sessions(self, agent_name: str, **_kw: object):
        return 1, [_SESSION]


class _FakeBatch:
    def __init__(self, *, inflight: dict[str, InflightEntry] | None = None) -> None:
        self._inflight = inflight or {}
        self.last_enqueue_all: dict[str, object] | None = None
        self.last_enqueue_sessions: list[str] | None = None

    def inflight(self, _agent: str) -> dict[str, InflightEntry]:
        return self._inflight

    async def derived_statuses(self, _agent: str, session_ids: list[str]) -> dict[str, str]:
        return dict.fromkeys(session_ids, "done")

    async def enqueue_all(self, _agent: str, **kw: object) -> EnqueueResult:
        self.last_enqueue_all = dict(kw)
        return EnqueueResult(queued=3, skipped=1, total=4)

    async def enqueue_sessions(self, _agent: str, session_ids: list[str]) -> EnqueueResult:
        self.last_enqueue_sessions = session_ids
        return EnqueueResult(queued=len(session_ids), skipped=0, total=len(session_ids))


def _app(batch: _FakeBatch) -> FastAPI:
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(distill_router)
    app.dependency_overrides[get_distill_service] = _FakeListService
    app.dependency_overrides[get_distill_batch_service] = lambda: batch
    app.dependency_overrides[get_distill_batch_service_optional] = lambda: batch
    app.dependency_overrides[require_token] = lambda: None
    return app


def test_list_overlays_inflight_over_derived() -> None:
    # sess-001 is "done" in the ledger but currently running → running wins.
    batch = _FakeBatch(inflight={"sess-001": InflightEntry(OpState.running)})
    with TestClient(_app(batch)) as c:
        r = c.get("/api/v1/agents/a/transcripts", headers=_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["sessions"][0]["distill_status"] == "running"


def test_distill_batch_all_returns_counts_and_202() -> None:
    batch = _FakeBatch()
    with TestClient(_app(batch)) as c:
        r = c.post(
            "/api/v1/agents/a/transcripts/distill-batch",
            json={"all": True, "q": "auth"},
            headers=_HEADERS,
        )
    assert r.status_code == 202, r.text
    assert r.json() == {"queued": 3, "skipped": 1, "total": 4}
    assert batch.last_enqueue_all == {
        "query": "auth",
        "project": None,
        "started_after": None,
        "started_before": None,
    }


def test_distill_batch_explicit_sessions() -> None:
    batch = _FakeBatch()
    with TestClient(_app(batch)) as c:
        r = c.post(
            "/api/v1/agents/a/transcripts/distill-batch",
            json={"session_ids": ["s1", "s2"]},
            headers=_HEADERS,
        )
    assert r.status_code == 202, r.text
    assert batch.last_enqueue_sessions == ["s1", "s2"]


def test_distill_status_lists_inflight() -> None:
    batch = _FakeBatch(
        inflight={
            "s1": InflightEntry(OpState.running),
            "s2": InflightEntry(OpState.error, "boom"),
        }
    )
    with TestClient(_app(batch)) as c:
        r = c.get("/api/v1/agents/a/transcripts/distill-status", headers=_HEADERS)
    assert r.status_code == 200, r.text
    by_id = {s["session_id"]: s for s in r.json()["statuses"]}
    assert by_id["s1"]["state"] == "running"
    assert by_id["s2"]["state"] == "error"
    assert by_id["s2"]["message"] == "boom"
