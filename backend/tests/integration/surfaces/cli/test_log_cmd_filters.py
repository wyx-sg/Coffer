"""`coffer log` asks each route what the Activity page asks (CLI-007).

Spec web-ui "Keep the command-line record readers": every filter the page sends
— search, event types, agent, raw server uid, severity, paging, counts — has an
option, and each lands in the request the reader makes.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from coffer.surfaces.cli import _client
from coffer.surfaces.cli.main import app

_runner = CliRunner()


class _Daemon:
    def __init__(self, answer: dict[str, Any]) -> None:
        self.answer = answer
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __enter__(self) -> _Daemon:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def get(self, path: str, **kw: Any) -> httpx.Response:
        self.calls.append((path, dict(kw.get("params") or {})))
        return httpx.Response(
            200, json=self.answer, request=httpx.Request("GET", f"http://d{path}")
        )


def _install(monkeypatch: pytest.MonkeyPatch, answer: dict[str, Any]) -> _Daemon:
    d = _Daemon(answer)
    monkeypatch.setattr(_client, "client_or_exit", lambda **_kw: (d, object()))
    return d


@pytest.mark.acceptance(
    spec="web-ui", scenario="every filter the Activity page sends has a reader option"
)
def test_log_daemon_sends_search_level_cursor_and_total(monkeypatch: pytest.MonkeyPatch) -> None:
    d = _install(
        monkeypatch,
        {"records": [], "next_cursor": "c2", "total": 7, "total_is_floor": True, "path": "/x"},
    )
    result = _runner.invoke(
        app,
        ["log", "daemon", "--q", "qa-cli", "--level", "warning", "--cursor", "c1", "--with-total"],
    )
    assert result.exit_code == 0, result.output
    path, params = d.calls[-1]
    assert path == "/daemon/logs"
    assert params["q"] == "qa-cli" and params["level"] == "warning"
    assert params["cursor"] == "c1" and params["with_total"] is True
    assert "at least 7 matching records" in result.stdout
    assert "--cursor c2" in result.stdout
    as_json = _runner.invoke(app, ["log", "daemon", "--json"])
    assert json.loads(as_json.stdout)["next_cursor"] == "c2"
    assert "with_total" not in d.calls[-1][1]


@pytest.mark.acceptance(
    spec="web-ui", scenario="every filter the Activity page sends has a reader option"
)
def test_log_audit_sends_search_and_event_types(monkeypatch: pytest.MonkeyPatch) -> None:
    d = _install(monkeypatch, {"entries": [], "next_cursor": None})
    result = _runner.invoke(
        app, ["log", "audit", "--q", "qa-cli", "--q-type", "a.b", "--q-type", "c.d", "--json"]
    )
    assert result.exit_code == 0, result.output
    assert d.calls[-1][1]["q"] == "qa-cli"
    assert d.calls[-1][1]["q_type"] == ["a.b", "c.d"]
    alone = _runner.invoke(app, ["log", "audit", "--q-type", "a.b"])
    assert alone.exit_code == 2
    assert len(d.calls) == 1


@pytest.mark.acceptance(
    spec="web-ui", scenario="every filter the Activity page sends has a reader option"
)
def test_log_mcp_sends_agent_uid_and_raw_uid(monkeypatch: pytest.MonkeyPatch) -> None:
    d = _install(monkeypatch, {"invocations": [], "next_cursor": None})
    result = _runner.invoke(
        app,
        ["log", "mcp", "--agent-uid", "a" * 26, "--uid", "coffer", "--q", "qa", "--json"],
    )
    assert result.exit_code == 0, result.output
    path, params = d.calls[-1]
    assert path == "/mcp/invocations"
    assert params == {"limit": 20, "agent_uid": "a" * 26, "uid": "coffer", "q": "qa"}
    clash = _runner.invoke(app, ["log", "mcp", "--server", "x", "--uid", "coffer"])
    assert clash.exit_code == 2
    assert len(d.calls) == 1
