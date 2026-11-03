"""How long the CLI waits for the daemon, and what it says when no answer comes.

ADR ``cli-request-wait-budgets``; spec resource-framework "Offer every
management operation on the command line". A real HTTP server on 127.0.0.1
stands in for a healthy daemon that answers after a set delay, so nothing here
depends on the network or on how long GitHub takes. The quick wait is made
short so the slow answer outlasts it in under a second.
"""

from __future__ import annotations

import json
import socket
import sys
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from coffer.application.skill.source_service import GIT_OPERATION_DEADLINE_S
from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli import _waits
from coffer.surfaces.cli import main as cli_main
from coffer.surfaces.cli._route_command import MOUNTED

_DELAY_S = 1.0


class _Slow(BaseHTTPRequestHandler):
    def _answer(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        time.sleep(_DELAY_S)
        body = json.dumps({"id": "stage-1", "skills": []}).encode()
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = _answer  # noqa: N815

    def log_message(self, *_args: object) -> None:
        pass


@pytest.fixture
def slow_daemon(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Slow)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}/api/v1"
    monkeypatch.setattr(
        _cli_client, "client_or_exit", lambda **_kw: (httpx.Client(base_url=base), object())
    )
    monkeypatch.setattr(_waits, "QUICK_S", 0.3)
    try:
        yield base
    finally:
        _waits.set_override(None)
        server.shutdown()
        server.server_close()


def _run(monkeypatch: pytest.MonkeyPatch, *argv: str) -> int:
    monkeypatch.setattr(sys, "argv", ["coffer", *argv])
    try:
        cli_main.run()
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


def _envelope(err: str) -> dict[str, object]:
    return dict(json.loads(err.strip().splitlines()[-1]))


_STAGE = ("skill", "stage-git", "--set", "url=https://example.com/r.git", "--json")


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a slow answer is reported as a timeout, not a crash"
)
def test_an_answer_slower_than_the_wait_exits_13_naming_the_request(
    slow_daemon: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run(monkeypatch, "skill", "list", "--json")

    assert code == 13
    error = _envelope(capsys.readouterr().err)["error"]
    assert isinstance(error, dict)
    assert error["code"] == "CLI_REQUEST_TIMEOUT"
    assert error["details"] == {"method": "GET", "path": "/skills", "waited_s": 0.3}
    assert "crashed" not in str(error["message"])


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a slow answer is reported as a timeout, not a crash"
)
def test_a_git_import_waits_past_the_quick_wait_for_its_answer(
    slow_daemon: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run(monkeypatch, *_STAGE)

    assert code == 0
    assert json.loads(capsys.readouterr().out)["id"] == "stage-1"


def test_request_timeout_replaces_the_commands_own_wait(
    slow_daemon: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys.modules[__name__], "_DELAY_S", 1.5)
    code = _run(monkeypatch, "--request-timeout", "1", *_STAGE)

    assert code == 13
    error = _envelope(capsys.readouterr().err)["error"]
    assert isinstance(error, dict)
    assert error["details"] == {"method": "POST", "path": "/skills/stage/git", "waited_s": 1.0}


def _closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a daemon that is not there is still unreachable"
)
def test_nothing_listening_is_daemon_unreachable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    base = f"http://127.0.0.1:{_closed_port()}/api/v1"
    monkeypatch.setattr(
        _cli_client, "client_or_exit", lambda **_kw: (httpx.Client(base_url=base), object())
    )
    code = _run(monkeypatch, *_STAGE)

    assert code == 3
    error = _envelope(capsys.readouterr().err)["error"]
    assert isinstance(error, dict) and error["code"] == "DAEMON_UNREACHABLE"


def test_every_git_source_command_waits_past_the_daemons_own_deadline() -> None:
    """The daemon's deadline answers first, so the CLI reports git's error."""
    assert _waits.GIT_S > GIT_OPERATION_DEADLINE_S
    git_routes = [
        c
        for c in MOUNTED
        if c.route == "/skills/stage/git"
        or (c.route.startswith("/skills/{uid}/source/") and not c.route.endswith("/apply"))
    ]
    assert {c.command for c in git_routes} == {
        "skill stage-git",
        "skill source check",
        "skill source change",
        "skill source handoff",
        "skill source merged",
    }
    assert all(c.wait == _waits.GIT_S for c in git_routes)
