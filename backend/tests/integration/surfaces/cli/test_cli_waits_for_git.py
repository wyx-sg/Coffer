"""A daemon waiting for git, seen from the command line (spec daemon "Wait in a
setup state when git is missing or too old").

A command that needs the daemon prints the setup message and the hand-off and
exits 10 before it sends its own request; ``coffer daemon status`` reports the
state and exits 0. The daemon's answers come from the real status route over
an in-process app in its setup state.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from typer.testing import CliRunner

from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.infrastructure.vault.git_requirement import FoundGit, GitCheck
from coffer.surfaces.cli import _client as cli_client
from coffer.surfaces.cli._options import ExitCode
from coffer.surfaces.cli.main import app
from coffer.surfaces.http import daemon_routes, setup_state
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token

_TOKEN = "cli-git-token"


@pytest.fixture
def waiting_daemon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    """A daemon in its setup state for a git 2.30, reachable through the CLI's seams."""
    monkeypatch.setenv("HOME", str(tmp_path))
    setup_state.enter_setup(
        GitCheck(usable=None, found=FoundGit(path="/usr/bin/git", version=(2, 30)))
    )
    set_active_token(_TOKEN)
    server = FastAPI()
    err_handlers.register(server)
    server.include_router(daemon_routes.router)
    setup_state.install(server)
    http = TestClient(server, base_url="http://localhost/api/v1")
    status = http.get("/daemon/status").json()
    info = DaemonInfo(
        version=1,
        pid=4242,
        port=9,  # nothing listens: a request the CLI sent would fail loudly
        token=_TOKEN,
        started_at=datetime.now(tz=UTC),
        binary_path="/test",
    )
    monkeypatch.setattr(cli_client, "live_daemon", lambda: info)
    monkeypatch.setattr(cli_client, "daemon_is_running", lambda: True)
    monkeypatch.setattr(cli_client, "probe_status", lambda _info, timeout: status)
    yield {"status": status, "http": http}
    setup_state.leave_setup()
    set_active_token(None)


@pytest.mark.acceptance(
    spec="daemon", scenario="a command that needs the daemon prints why it waits"
)
def test_a_command_prints_the_setup_message_and_exits_10(waiting_daemon: dict[str, Any]) -> None:
    res = CliRunner().invoke(app, ["vault", "problems"])
    assert res.exit_code == int(ExitCode.GIT_NEEDED) == 10, res.output
    setup = waiting_daemon["status"]["setup"]
    assert setup["message"] in res.stderr
    assert "the git on this machine is 2.30" in res.stderr
    assert "To hand this to your agent, give it this prompt:" in res.stderr
    assert setup["handoff"]["prompt"] in res.stderr
    assert res.stdout == ""


def test_daemon_status_reports_the_setup_state(
    waiting_daemon: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    http: TestClient = waiting_daemon["http"]

    def _connect(**_kwargs: object) -> tuple[TestClient, DaemonInfo]:
        info = cli_client.live_daemon()
        assert info is not None
        return http, info

    monkeypatch.setattr(cli_client, "client_or_exit", _connect)
    res = CliRunner().invoke(app, ["daemon", "status"])
    assert res.exit_code == 0, res.output
    assert "status:  setup" in res.stdout
    assert waiting_daemon["status"]["setup"]["message"] in res.stderr

    res = CliRunner().invoke(app, ["daemon", "status", "--json"])
    body = json.loads(res.stdout)
    assert body["status"] == "setup" and body["setup"]["reason"] == "git_too_old"
    assert body["passes_in_flight"] == []
