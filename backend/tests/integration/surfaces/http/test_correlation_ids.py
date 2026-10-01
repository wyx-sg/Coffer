"""One trace id joins the audit log, the MCP invocation log and the daemon log.

Spec resource-framework "Correlate the audit log, the MCP invocation log and
the daemon log by one trace id". Boots the full app under a throwaway HOME with
its log directory in ``tmp_path``, drives a plain REST mutation and an MCP tool
call that writes, and reads each record back over REST and through the
command line — the three logs a person joins when asking "what else did this
request do?".
"""

from __future__ import annotations

import json
import logging
import pathlib
from collections.abc import Iterator
from typing import Any

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli import _client as cli_client
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.trace import TRACE_HEADER

_TOKEN = "test-token-correlation"
_HEADERS = {"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "user"}
_runner = CliRunner()


@pytest.fixture
def client(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59850")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59859")
    root = logging.getLogger()
    saved = root.handlers[:]
    app = create_app()
    set_active_token(_TOKEN)
    with TestClient(app, base_url="http://localhost", headers=_HEADERS) as c:
        yield c
    for handler in root.handlers:
        if handler not in saved:
            handler.close()
    root.handlers = saved
    set_active_token(None)


def _mcp(
    c: TestClient, session: str | None, method: str, params: dict[str, Any], trace: str
) -> Any:
    headers = {**_HEADERS, TRACE_HEADER: trace, **({"Mcp-Session-Id": session} if session else {})}
    r = c.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r


class _Api:
    """The running app as the CLI's client: paths under ``/api/v1``, and a
    ``with`` block that does not start or stop the app's lifespan again."""

    def __init__(self, c: TestClient) -> None:
        self._c = c

    def __enter__(self) -> _Api:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def get(self, path: str, **kwargs: Any) -> Any:
        return self._c.get(f"/api/v1{path}", **kwargs)


def _cli(c: TestClient, monkeypatch: pytest.MonkeyPatch, *args: str) -> Any:
    """Run ``coffer <args>`` against this same app, as ``in_proc_daemon`` does."""
    api = _Api(c)
    info = DaemonInfo(version=1, pid=1, port=0, token=_TOKEN, started_at=None, binary_path="")  # type: ignore[arg-type]
    monkeypatch.setattr(cli_client, "client_or_exit", lambda: (api, info))
    monkeypatch.setattr(cli_client, "daemon_is_running", lambda: True)
    result = _runner.invoke(cli_app, list(args), env={"COLUMNS": "250"})
    assert result.exit_code == 0, result.output
    return result


def _flush_logs() -> None:
    for handler in logging.getLogger().handlers:
        handler.flush()


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a request's audit rows carry its trace id"
)
def test_a_requests_audit_row_and_log_line_carry_its_trace_id(client: TestClient) -> None:
    made = client.post(
        "/api/v1/knowledge/collections", json={"name": "traced"}, headers={TRACE_HEADER: "req-a1"}
    )
    assert made.status_code == 201, made.text
    assert made.headers[TRACE_HEADER] == "req-a1"

    page = client.get("/api/v1/audit", params={"trace_id": "req-a1"}).json()
    assert page["total"] >= 1
    assert {e["trace_id"] for e in page["entries"]} == {"req-a1"}
    assert any(e["event_type"] == "resource_created" for e in page["entries"])
    # A row written by another request is not in the filter's answer.
    client.post("/api/v1/knowledge/collections", json={"name": "other"})
    assert (
        client.get("/api/v1/audit", params={"trace_id": "req-a1"}).json()["total"] == page["total"]
    )

    _flush_logs()
    logs = client.get("/api/v1/daemon/logs", params={"trace_id": "req-a1", "limit": 500}).json()
    assert logs["records"], "the audit mirror line carries the request's trace id"
    assert {r["record"]["trace_id"] for r in logs["records"]} == {"req-a1"}


@pytest.mark.acceptance(
    spec="resource-framework", scenario="an MCP call's records carry its session and trace id"
)
def test_an_mcp_calls_invocation_audit_row_and_log_share_one_trace_id(client: TestClient) -> None:
    assert client.post("/api/v1/knowledge/collections", json={"name": "notes"}).status_code == 201
    session = _mcp(client, None, "initialize", {}, "init-1").headers["mcp-session-id"]
    called = _mcp(
        client,
        session,
        "tools/call",
        {
            "name": "coffer__write",
            "arguments": {
                "collection": "notes",
                "title": "Build host",
                "description": "Where the build runs",
                "body": "On the mini.",
            },
        },
        "mcp-call-7",
    ).json()
    assert called["result"].get("isError") is not True, called

    calls = client.get("/api/v1/mcp/invocations", params={"trace_id": "mcp-call-7"}).json()
    [call] = calls["invocations"]
    assert call["capability_key"] == "write"
    assert call["session_id"] == session
    assert call["trace_id"] == "mcp-call-7"

    audit = client.get("/api/v1/audit", params={"trace_id": "mcp-call-7"}).json()["entries"]
    assert audit, "the write the tool made is audited under the call's trace id"
    assert {e["trace_id"] for e in audit} == {"mcp-call-7"}

    _flush_logs()
    lines = client.get("/api/v1/daemon/logs", params={"trace_id": "mcp-call-7"}).json()["records"]
    assert lines
    assert all(r["record"].get("session_id") == session for r in lines)


@pytest.mark.acceptance(
    spec="resource-framework", scenario="the command line filters each log by trace id"
)
def test_the_command_line_filters_each_log_by_trace_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert client.post("/api/v1/knowledge/collections", json={"name": "notes"}).status_code == 201
    session = _mcp(client, None, "initialize", {}, "init-2").headers["mcp-session-id"]
    _mcp(
        client,
        session,
        "tools/call",
        {
            "name": "coffer__write",
            "arguments": {"collection": "notes", "title": "T", "description": "D", "body": "B"},
        },
        "cli-trace-3",
    )
    _flush_logs()

    audit = json.loads(
        _cli(client, monkeypatch, "log", "audit", "--trace", "cli-trace-3", "--json").output
    )
    assert audit["entries"] and {e["trace_id"] for e in audit["entries"]} == {"cli-trace-3"}
    table = _cli(client, monkeypatch, "log", "audit", "--trace", "cli-trace-3").output
    assert "cli-trace-3" in table

    mcp = json.loads(
        _cli(client, monkeypatch, "log", "mcp", "--trace", "cli-trace-3", "--json").output
    )
    assert [i["trace_id"] for i in mcp["invocations"]] == ["cli-trace-3"]

    daemon = json.loads(
        _cli(client, monkeypatch, "log", "daemon", "--trace", "cli-trace-3", "--json").output
    )
    assert daemon["records"]
    assert {r["record"]["trace_id"] for r in daemon["records"]} == {"cli-trace-3"}
