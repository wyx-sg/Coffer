"""Integration tests for `coffer agent transcripts`.

FR-009/FR-010 require every agent-workspace op to exist on BOTH REST and CLI;
this verb wraps the one read-only route:

  ``GET /agents/{name}/transcripts`` → ``transcripts``

Like the rest of the CLI suite we stub the HTTP layer: a tiny fake client
returns canned ``GET`` responses and ``_client.client_or_exit`` is
monkeypatched to hand it back. No daemon, and — importantly — no walk of the
developer's real ``~/.claude`` / ``~/.codex`` transcripts.
"""

from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime as dt
from typing import Any

from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app as cli_app

_runner = CliRunner()

SESSION = {
    "session_id": "a1",
    "title": "fix the alpha login bug",
    "project_path": "/proj/alpha",
    "message_count": 12,
    "started_at": "2026-05-01T09:30:00Z",
    "last_activity_at": "2026-05-09T18:05:00Z",
    "source_path": "/home/u/.codex/sessions/2026/05/rollout-a1.jsonl",
}


class _FakeResponse:
    """Minimal stand-in for ``httpx.Response`` as the CLI consumes it."""

    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = b"x"

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:  # pragma: no cover - not exercised
            import httpx

            request = httpx.Request("GET", "http://test/")
            raise httpx.HTTPStatusError(
                "error",
                request=request,
                response=httpx.Response(self.status_code, json=self._payload, request=request),
            )


class _FakeClient:
    """Records GET calls and replays canned responses keyed by path."""

    def __init__(self, get_map: dict[str, _FakeResponse]):
        self._get_map = get_map
        self.calls: list[tuple[str, str, Any]] = []

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def get(self, path: str, **kw: Any) -> _FakeResponse:
        self.calls.append(("GET", path, kw))
        return self._get_map[path]


def _install(monkeypatch, *, get_map=None) -> _FakeClient:
    client = _FakeClient(get_map or {})
    info = DaemonInfo(
        version=1,
        pid=1,
        port=8000,
        token="t",
        started_at=dt.now(tz=UTC),
        binary_path="/t",
    )
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (client, info))
    return client


def _page(sessions: list[dict[str, Any]], total: int | None = None) -> _FakeResponse:
    return _FakeResponse(
        200,
        {
            "sessions": sessions,
            "total": total if total is not None else len(sessions),
            "limit": 20,
            "offset": 0,
        },
    )


def test_transcripts_json(monkeypatch):
    """`transcripts <name> --json` prints the raw response verbatim."""
    _install(monkeypatch, get_map={"/agents/cx/transcripts": _page([SESSION], total=3)})

    result = _runner.invoke(cli_app, ["agent", "transcripts", "cx", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "sessions": [SESSION],
        "total": 3,
        "limit": 20,
        "offset": 0,
    }


def test_transcripts_table(monkeypatch):
    """`transcripts <name>` renders title, project, count, and short times."""
    monkeypatch.setenv("COLUMNS", "200")  # don't let rich wrap the assertions apart
    _install(monkeypatch, get_map={"/agents/cx/transcripts": _page([SESSION], total=3)})

    result = _runner.invoke(cli_app, ["agent", "transcripts", "cx"])
    assert result.exit_code == 0, result.output
    assert "fix the alpha login bug" in result.output
    assert "/proj/alpha" in result.output
    assert "12" in result.output
    assert "2026-05-01 09:30" in result.output  # seconds trimmed for the table
    assert "1 of 3" in result.output  # page size vs matched total


def test_transcripts_untitled_row_falls_back_to_session_id(monkeypatch):
    """A session the agent never titled still identifies itself in the table."""
    monkeypatch.setenv("COLUMNS", "200")
    untitled = {**SESSION, "title": None, "started_at": None, "last_activity_at": None}
    _install(monkeypatch, get_map={"/agents/cx/transcripts": _page([untitled])})

    result = _runner.invoke(cli_app, ["agent", "transcripts", "cx"])
    assert result.exit_code == 0, result.output
    assert "a1" in result.output


def test_transcripts_forwards_query_sort_and_paging(monkeypatch):
    """Search/sort/paging options travel as query params, not client-side."""
    client = _install(monkeypatch, get_map={"/agents/cx/transcripts": _page([SESSION])})

    result = _runner.invoke(
        cli_app,
        [
            "agent",
            "transcripts",
            "cx",
            "-q",
            "alpha",
            "--sort",
            "started_at",
            "--order",
            "asc",
            "--limit",
            "5",
            "--offset",
            "10",
        ],
    )
    assert result.exit_code == 0, result.output
    assert client.calls == [
        (
            "GET",
            "/agents/cx/transcripts",
            {
                "params": {
                    "limit": 5,
                    "offset": 10,
                    "sort": "started_at",
                    "order": "asc",
                    "q": "alpha",
                }
            },
        )
    ]


def test_transcripts_unknown_agent_exits_4(monkeypatch):
    """A 404 from the daemon exits 4 with the server's message."""
    _install(
        monkeypatch,
        get_map={
            "/agents/ghost/transcripts": _FakeResponse(
                404, {"error": {"code": "RESOURCE_NOT_FOUND", "message": "agent 'ghost' not found"}}
            )
        },
    )

    result = _runner.invoke(cli_app, ["agent", "transcripts", "ghost"])
    assert result.exit_code == 4, result.output
    assert "not found" in result.output


def test_transcripts_is_registered():
    """The read verb appears under `coffer agent` (FR-009 CLI/REST parity)."""
    help_out = _runner.invoke(cli_app, ["agent", "--help"]).output
    assert "transcripts" in help_out
