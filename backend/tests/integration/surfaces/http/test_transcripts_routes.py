"""Integration tests for /api/v1/agents/{name}/transcripts routes (Spec 007 / ADR-020).

Uses a minimal FastAPI app with the distill + auth routers only, with the
distill service injected via dependency_overrides — no DB, no filesystem.
Mirrors the pattern in tests/integration/chat/test_http_routes.py.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from coffer.application.distill.service import DistillResult, NoModelConfiguredError
from coffer.domain.distill.locations import UnsupportedAgentTypeError
from coffer.domain.distill.session import DistilledInsight, InsightType, TranscriptSession
from coffer.domain.errors import ResourceNotFound
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import require_token, set_active_token
from coffer.surfaces.http.distill.routes import router as distill_router
from coffer.surfaces.http.distill.state import get_distill_service

_TOKEN = "transcripts-test-token"
_HEADERS = {"X-Coffer-Token": _TOKEN}


# ---------------------------------------------------------------------------
# Fake service
# ---------------------------------------------------------------------------


class _FakeDistillService:
    """Minimal stub that covers the happy path and key error cases."""

    def __init__(
        self,
        *,
        sessions: list[TranscriptSession] | None = None,
        distill_result: DistillResult | None = None,
        raise_on_list: Exception | None = None,
        raise_on_distill: Exception | None = None,
    ) -> None:
        self._sessions = sessions or []
        self._distill_result = distill_result or DistillResult()
        self._raise_on_list = raise_on_list
        self._raise_on_distill = raise_on_distill

    async def list_sessions(
        self, agent_name: str, *, limit: int = 100, offset: int = 0
    ) -> tuple[int, list[TranscriptSession]]:
        if self._raise_on_list is not None:
            raise self._raise_on_list
        total = len(self._sessions)
        return total, self._sessions[offset : offset + limit]

    async def distill(
        self,
        *,
        agent_name: str,
        session_id: str | None = None,
        project_path: str | None = None,
        model_id: str | None = None,
        dry_run: bool = False,
    ) -> DistillResult:
        if self._raise_on_distill is not None:
            raise self._raise_on_distill
        if dry_run:
            # Return insights but no fact ids (dry-run contract)
            return DistillResult(insights=self._distill_result.insights, facts=[])
        return self._distill_result


def _build_app(svc: _FakeDistillService) -> FastAPI:
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(distill_router)
    app.dependency_overrides[get_distill_service] = lambda: svc
    app.dependency_overrides[require_token] = lambda: None  # skip token check
    return app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SESSION = TranscriptSession(
    session_id="sess-001",
    agent_type_value="claude_code",
    project_path="/home/user/my-repo",
    started_at=datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC),
    messages=(),
    source_path="/home/user/.claude/projects/-home-user-my-repo/abc.jsonl",
)

_INSIGHT = DistilledInsight(
    name="Use ULIDs for IDs",
    description="Project standard for identifiers",
    body="All IDs in this project are ULIDs, not UUIDs.",
    type=InsightType.CONVENTION,
)

_RESULT = DistillResult(insights=[_INSIGHT], facts=["fact-id-001"])


# ---------------------------------------------------------------------------
# GET /api/v1/agents/{name}/transcripts
# ---------------------------------------------------------------------------


def test_list_transcripts_returns_sessions() -> None:
    set_active_token(_TOKEN)
    svc = _FakeDistillService(sessions=[_SESSION])
    app = _build_app(svc)
    with TestClient(app) as c:
        r = c.get("/api/v1/agents/my-agent/transcripts", headers=_HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "sessions" in body
    assert len(body["sessions"]) == 1
    sess = body["sessions"][0]
    assert sess["session_id"] == "sess-001"
    assert sess["project_path"] == "/home/user/my-repo"
    assert sess["message_count"] == 0
    assert sess["started_at"] is not None
    # Paged response carries the total count + echoes the window.
    assert body["total"] == 1
    assert body["limit"] == 100
    assert body["offset"] == 0


def test_list_transcripts_honors_limit_and_offset() -> None:
    set_active_token(_TOKEN)
    svc = _FakeDistillService(sessions=[_SESSION, _SESSION, _SESSION])
    app = _build_app(svc)
    with TestClient(app) as c:
        r = c.get(
            "/api/v1/agents/my-agent/transcripts?limit=2&offset=1",
            headers=_HEADERS,
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 1
    assert len(body["sessions"]) == 2


def test_list_transcripts_empty() -> None:
    set_active_token(_TOKEN)
    svc = _FakeDistillService(sessions=[])
    app = _build_app(svc)
    with TestClient(app) as c:
        r = c.get("/api/v1/agents/no-agent/transcripts", headers=_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["sessions"] == []


def test_list_transcripts_agent_not_found_returns_envelope() -> None:
    set_active_token(_TOKEN)
    svc = _FakeDistillService(raise_on_list=ResourceNotFound("agent", "ghost"))
    app = _build_app(svc)
    with TestClient(app) as c:
        r = c.get("/api/v1/agents/ghost/transcripts", headers=_HEADERS)
    assert r.status_code == 404, r.text
    body = r.json()
    assert body["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_list_transcripts_unsupported_agent_type_returns_envelope() -> None:
    set_active_token(_TOKEN)
    svc = _FakeDistillService(raise_on_list=UnsupportedAgentTypeError("nonexistent_agent"))
    app = _build_app(svc)
    with TestClient(app) as c:
        r = c.get("/api/v1/agents/nonexistent-agent/transcripts", headers=_HEADERS)
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["error"]["code"] == "UNSUPPORTED_AGENT_TYPE"


# ---------------------------------------------------------------------------
# POST /api/v1/agents/{name}/transcripts/distill
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="007-memory", scenario="distill-transcript-to-memory")
def test_distill_returns_insights_and_fact_ids() -> None:
    set_active_token(_TOKEN)
    svc = _FakeDistillService(distill_result=_RESULT)
    app = _build_app(svc)
    with TestClient(app) as c:
        r = c.post(
            "/api/v1/agents/my-agent/transcripts/distill",
            json={"session_id": "sess-001"},
            headers=_HEADERS,
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["insights"]) == 1
    insight = body["insights"][0]
    assert insight["name"] == "Use ULIDs for IDs"
    assert insight["type"] == "convention"
    assert body["fact_ids"] == ["fact-id-001"]


def test_distill_dry_run_returns_insights_no_fact_ids() -> None:
    set_active_token(_TOKEN)
    svc = _FakeDistillService(distill_result=_RESULT)
    app = _build_app(svc)
    with TestClient(app) as c:
        r = c.post(
            "/api/v1/agents/my-agent/transcripts/distill",
            json={"session_id": "sess-001", "dry_run": True},
            headers=_HEADERS,
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["insights"]) == 1
    assert body["fact_ids"] == []


def test_distill_agent_not_found_returns_envelope() -> None:
    set_active_token(_TOKEN)
    svc = _FakeDistillService(raise_on_distill=ResourceNotFound("agent", "ghost"))
    app = _build_app(svc)
    with TestClient(app) as c:
        r = c.post(
            "/api/v1/agents/ghost/transcripts/distill",
            json={"session_id": "s1"},
            headers=_HEADERS,
        )
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_distill_unsupported_agent_type_returns_envelope() -> None:
    set_active_token(_TOKEN)
    svc = _FakeDistillService(raise_on_distill=UnsupportedAgentTypeError("nonexistent_agent"))
    app = _build_app(svc)
    with TestClient(app) as c:
        r = c.post(
            "/api/v1/agents/nonexistent-agent/transcripts/distill",
            json={"session_id": "s1"},
            headers=_HEADERS,
        )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "UNSUPPORTED_AGENT_TYPE"


def test_distill_no_model_configured_returns_envelope() -> None:
    set_active_token(_TOKEN)
    svc = _FakeDistillService(raise_on_distill=NoModelConfiguredError("No model configured."))
    app = _build_app(svc)
    with TestClient(app) as c:
        r = c.post(
            "/api/v1/agents/my-agent/transcripts/distill",
            json={"session_id": "s1"},
            headers=_HEADERS,
        )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "NO_MODEL_CONFIGURED"


def test_distill_session_not_found_returns_envelope() -> None:
    set_active_token(_TOKEN)
    svc = _FakeDistillService(raise_on_distill=KeyError("session-missing"))
    app = _build_app(svc)
    with TestClient(app) as c:
        r = c.post(
            "/api/v1/agents/my-agent/transcripts/distill",
            json={"session_id": "session-missing"},
            headers=_HEADERS,
        )
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "TRANSCRIPT_SESSION_NOT_FOUND"
