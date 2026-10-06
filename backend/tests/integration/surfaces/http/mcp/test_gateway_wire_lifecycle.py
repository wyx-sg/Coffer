"""The gateway's lifecycle at the wire: timeouts, launch failures, children, load.

Spec mcp-gateway. A real daemon app, real ledger upstreams
(``tests/fixtures/ledger_mcp_server.py``, read through ``tests/support/ledger_wire.py``)
and raw JSON-RPC, so each assertion names the exact code and the upstream's
own count of what it ran.
"""

from __future__ import annotations

import http.server
import os
import pathlib
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from tests.support.boundary_daemon import BoundaryDaemon, prepare_home, running_daemon
from tests.support.ledger_wire import (
    call,
    code,
    events,
    ledger_transport,
    open_session,
    register,
    result,
    rpc,
    wait_for,
)

pytestmark = pytest.mark.timeout(180)


@pytest.fixture
def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryDaemon]:
    db = prepare_home(tmp_path, monkeypatch)
    with running_daemon(tmp_path, db) as d:
        yield d


@pytest.fixture
def ledger(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "ledger.jsonl"
    path.touch()
    return path


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def test_upstream_past_its_request_timeout_is_answered_internal_error_once(
    daemon: BoundaryDaemon, ledger: pathlib.Path
) -> None:
    # request_timeout_seconds has a floor of 5 (server_config.py), so 5 s / an 8 s call.
    register(daemon, "up", ledger_transport(ledger), request_timeout_seconds=5)
    session = open_session(daemon)
    t0 = time.perf_counter()
    reply = call(daemon, session, "up__slow", {"delay": 8})
    elapsed = time.perf_counter() - t0
    assert code(reply) == -32603, reply.text
    assert elapsed < 8
    assert len(events(ledger, "start", "slow")) == 1


@pytest.mark.parametrize(
    "case",
    ["missing-command", "missing-cwd", "exit"],
)
def test_upstream_that_cannot_start_is_answered_with_an_error_within_a_bound(
    daemon: BoundaryDaemon, ledger: pathlib.Path, tmp_path: pathlib.Path, case: str
) -> None:
    if case == "missing-command":
        transport: dict[str, Any] = {"type": "stdio", "command": "/qa-missing-command"}
    elif case == "missing-cwd":
        transport = ledger_transport(ledger, cwd=str(tmp_path / "no-such-dir"))
    else:
        transport = ledger_transport(ledger, "--mode", "exit")
    register(daemon, "up", transport, spawn_timeout_seconds=5)
    session = open_session(daemon)
    t0 = time.perf_counter()
    reply = call(daemon, session, "up__echo", {"text": "qa"})
    assert time.perf_counter() - t0 < 30
    assert reply.status_code == 200
    assert "error" in reply.json(), reply.text
    assert events(ledger, "start", "echo") == []


@pytest.mark.parametrize("mode", ["pollute", "invalid-json"])
def test_upstream_that_writes_one_bad_stdout_line_still_answers_the_call(
    daemon: BoundaryDaemon, ledger: pathlib.Path, mode: str
) -> None:
    # Observed product behaviour: the SDK's stdio client skips a non-JSON line, so the
    # upstream's real answer arrives and the call succeeds (not an error).
    register(daemon, "up", ledger_transport(ledger, "--mode", mode), spawn_timeout_seconds=5)
    session = open_session(daemon)
    t0 = time.perf_counter()
    reply = call(daemon, session, "up__echo", {"text": "qa"})
    assert time.perf_counter() - t0 < 30
    assert result(reply)["structuredContent"]["arguments"] == {"text": "qa"}
    assert len(events(ledger, "start", "echo")) == 1


class _Fault(http.server.BaseHTTPRequestHandler):
    def _fault(self) -> None:
        if self.server.mode == "status":  # type: ignore[attr-defined]
            self.send_response(503)
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self.close_connection = True
            self.connection.close()

    do_GET = do_POST = do_DELETE = _fault  # noqa: N815

    def log_message(self, *args: Any) -> None:
        return None


@pytest.mark.parametrize("mode", ["status", "drop"])
def test_http_upstream_that_fails_is_answered_with_an_error_within_a_bound(
    daemon: BoundaryDaemon, mode: str
) -> None:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Fault)
    server.mode = mode  # type: ignore[attr-defined]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/mcp"
        register(daemon, "fault", {"type": "http", "url": url}, spawn_timeout_seconds=5)
        session = open_session(daemon)
        t0 = time.perf_counter()
        reply = call(daemon, session, "fault__echo", {"text": "qa"})
        assert time.perf_counter() - t0 < 60
        assert reply.status_code == 200
        assert "error" in reply.json(), reply.text
    finally:
        server.shutdown()
        server.server_close()


def test_deleting_a_server_leaves_no_child_in_any_session(
    daemon: BoundaryDaemon, ledger: pathlib.Path
) -> None:
    uid = register(daemon, "up", ledger_transport(ledger))
    sessions = [open_session(daemon) for _ in range(2)]
    for s in sessions:
        assert "result" in call(daemon, s, "up__echo", {"text": "spawn"}).json()
    pids = {row["pid"] for row in events(ledger, "start", "echo")}
    assert len(pids) == 2, "each session spawns its own child"
    assert all(_alive(p) for p in pids)

    assert daemon.client.delete(f"/api/v1/resources/{uid}").status_code == 204

    wait_for(lambda: not any(_alive(p) for p in pids), "every child to exit", seconds=10)
    assert code(call(daemon, sessions[0], "up__echo", {"text": "after delete"})) == -32602


def test_forty_concurrent_calls_each_get_their_own_answer(
    daemon: BoundaryDaemon, ledger: pathlib.Path
) -> None:
    register(daemon, "up", ledger_transport(ledger))
    session = open_session(daemon)

    def one(i: int) -> Any:
        return call(daemon, session, "up__echo", {"text": f"qa {i}"})

    with ThreadPoolExecutor(4) as pool:
        replies = list(pool.map(one, range(40)))
    for i, reply in enumerate(replies):
        assert result(reply)["structuredContent"]["arguments"]["text"] == f"qa {i}"
    assert len(events(ledger, "start", "echo")) == 40


def test_eight_sessions_in_a_row_are_distinct_and_each_answered(
    daemon: BoundaryDaemon, ledger: pathlib.Path
) -> None:
    register(daemon, "up", ledger_transport(ledger))
    sessions = [open_session(daemon) for _ in range(8)]
    assert len(set(sessions)) == 8
    for i, s in enumerate(sessions):
        got = result(call(daemon, s, "up__echo", {"text": str(i)}))
        assert got["structuredContent"]["arguments"] == {"text": str(i)}
    assert rpc(daemon, sessions[0], "ping", {}).status_code == 200
