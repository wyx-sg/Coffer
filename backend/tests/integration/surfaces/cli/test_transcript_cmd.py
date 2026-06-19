"""Integration tests for `coffer transcript ...` CLI subcommands (Spec 007 / ADR-020).

Stubs the distill service via dependency_overrides so no DB, no filesystem, no LLM.
Mirrors the pattern from test_memory_cmd.py (monkeypatch _cli_client.client_or_exit)
and test_transcripts_routes.py (fake service + minimal FastAPI app).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.application.distill.service import DistillResult
from coffer.domain.distill.session import DistilledInsight, InsightType, TranscriptSession
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import require_token, set_active_token
from coffer.surfaces.http.distill.routes import router as distill_router
from coffer.surfaces.http.distill.state import get_distill_service

_runner = CliRunner()
_TOKEN = "test-token-transcript-cli"
_HEADERS = {"X-Coffer-Token": _TOKEN}


# ---------------------------------------------------------------------------
# Fake distill service
# ---------------------------------------------------------------------------


class _FakeDistillService:
    def __init__(
        self,
        *,
        sessions: list[TranscriptSession] | None = None,
        distill_result: DistillResult | None = None,
    ) -> None:
        self._sessions = sessions or []
        self._distill_result = distill_result or DistillResult()

    async def list_sessions(
        self, agent_name: str, *, limit: int = 100, offset: int = 0
    ) -> tuple[int, list[TranscriptSession]]:
        return len(self._sessions), self._sessions[offset : offset + limit]

    async def distill(
        self,
        *,
        agent_name: str,
        session_id: str | None = None,
        project_path: str | None = None,
        model_id: str | None = None,
        dry_run: bool = False,
    ) -> DistillResult:
        if dry_run:
            return DistillResult(insights=self._distill_result.insights, facts=[])
        return self._distill_result


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

_SESSION = TranscriptSession(
    session_id="sess-abc",
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


def _build_app(svc: _FakeDistillService) -> FastAPI:
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(distill_router)
    app.dependency_overrides[get_distill_service] = lambda: svc
    app.dependency_overrides[require_token] = lambda: None
    return app


@pytest.fixture
def transcript_cli_daemon(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    """In-process daemon with distill routes; monkeypatches client_or_exit."""
    svc = _FakeDistillService(sessions=[_SESSION], distill_result=_RESULT)
    fapp = _build_app(svc)
    set_active_token(_TOKEN)

    info = DaemonInfo(
        version=1,
        pid=12345,
        port=59900,
        token=_TOKEN,
        started_at=datetime.now(tz=UTC),
        binary_path="/test",
    )

    fake_client = TestClient(
        fapp,
        base_url="http://localhost/api/v1",
        headers=_HEADERS,
        raise_server_exceptions=False,
    )

    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (fake_client, info))

    yield

    set_active_token(None)


# ---------------------------------------------------------------------------
# Tests: transcript list
# ---------------------------------------------------------------------------


def test_list_renders_session_row(transcript_cli_daemon: None) -> None:
    result = _runner.invoke(cli_app, ["transcript", "list", "my-agent"])
    assert result.exit_code == 0, result.output
    assert "sess-abc" in result.output
    assert "/home/user/my-repo" in result.output


def test_list_shows_message_count(transcript_cli_daemon: None) -> None:
    result = _runner.invoke(cli_app, ["transcript", "list", "my-agent"])
    assert result.exit_code == 0, result.output
    # message_count == 0 for _SESSION (empty messages tuple)
    assert "0" in result.output


# ---------------------------------------------------------------------------
# Tests: transcript distill
# ---------------------------------------------------------------------------


def test_distill_dry_run_prints_insights(transcript_cli_daemon: None) -> None:
    result = _runner.invoke(
        cli_app, ["transcript", "distill", "my-agent", "--session", "sess-abc", "--dry-run"]
    )
    assert result.exit_code == 0, result.output
    assert "Use ULIDs for IDs" in result.output
    assert "convention" in result.output
    assert "dry-run" in result.output


def test_distill_dry_run_does_not_print_fact_ids(transcript_cli_daemon: None) -> None:
    result = _runner.invoke(
        cli_app, ["transcript", "distill", "my-agent", "--session", "sess-abc", "--dry-run"]
    )
    assert result.exit_code == 0, result.output
    # "fact-id-001" must NOT appear — dry-run writes nothing
    assert "fact-id-001" not in result.output


def test_distill_real_run_prints_fact_ids(transcript_cli_daemon: None) -> None:
    result = _runner.invoke(cli_app, ["transcript", "distill", "my-agent", "--session", "sess-abc"])
    assert result.exit_code == 0, result.output
    assert "fact-id-001" in result.output
    assert "Use ULIDs for IDs" in result.output


def test_distill_real_run_prints_body(transcript_cli_daemon: None) -> None:
    result = _runner.invoke(cli_app, ["transcript", "distill", "my-agent", "--session", "sess-abc"])
    assert result.exit_code == 0, result.output
    assert "ULIDs" in result.output
