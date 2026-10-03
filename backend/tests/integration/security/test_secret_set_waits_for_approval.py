"""`coffer secret set` when the value it stores waits for a person, against a real
in-process daemon over a throwaway HOME (spec secret "Answer a pending approval on the
command line by waiting or exiting")."""

from __future__ import annotations

import pathlib
import time
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from coffer.surfaces.cli import _approvals
from coffer.surfaces.cli.main import app as cli_app
from tests.support.boundary_daemon import (
    BoundaryDaemon,
    point_cli_at,
    prepare_home,
    running_daemon,
)

_runner = CliRunner()


@pytest.fixture
def cli(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryDaemon]:
    db = prepare_home(tmp_path, monkeypatch)
    with running_daemon(tmp_path, db) as d:
        point_cli_at(d, monkeypatch)
        yield d


def _approve_while_waiting(d: BoundaryDaemon, monkeypatch: pytest.MonkeyPatch) -> None:
    """Approve every pending request each time ``--wait`` pauses between polls.

    Only the CLI's own wait loop sees the stand-in clock; patching ``time.sleep`` on
    the shared ``time`` module would hand it to every thread in the process.
    """

    def the_person_approves(_seconds: float) -> None:
        for approval in d.pending():
            d.approve(approval["id"])

    fake = SimpleNamespace(monotonic=time.monotonic, sleep=the_person_approves)
    monkeypatch.setattr(_approvals, "time", fake)


@pytest.mark.acceptance(
    spec="secret", scenario="the command line reports a pending approval and exits 9"
)
def test_the_command_line_reports_a_pending_approval_and_exits_9(cli: BoundaryDaemon) -> None:
    d = cli
    d.store("gh/token", "ghp_cli_value_1")
    d.register_stdio("first", "server-one", {"TOKEN": "gh/token"})
    d.pending()

    r = _runner.invoke(cli_app, ["secret", "set", "gh/token", "--value", "ghp_cli_value_2"])

    assert r.exit_code == 9, r.output
    assert "waiting for approval in the Coffer app" in r.stderr
    [waiting] = d.pending()
    assert waiting["op"] == "replace_value" and waiting["id"] in r.stderr
    listed = d.client.get("/api/v1/secrets/approvals").json()["approvals"]
    assert [a["id"] for a in listed] == [waiting["id"]]
    # The stored value keeps its old bytes until a person approves.
    assert d.value("gh/token") == "ghp_cli_value_1"


@pytest.mark.acceptance(
    spec="secret", scenario="the command line waits for the approval with --wait"
)
def test_the_command_line_waits_for_the_approval(
    cli: BoundaryDaemon, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = cli
    d.store("gh/token", "ghp_cli_value_3")
    d.register_stdio("first", "server-one", {"TOKEN": "gh/token"})
    d.pending()

    _approve_while_waiting(d, monkeypatch)
    r = _runner.invoke(
        cli_app, ["secret", "set", "gh/token", "--value", "ghp_cli_value_4", "--wait"]
    )

    assert r.exit_code == 0, r.output
    assert "approved in the Coffer app" in r.stderr
    assert d.value("gh/token") == "ghp_cli_value_4"


@pytest.mark.acceptance(
    spec="secret", scenario="the command line reports a pending provider key and exits 9"
)
def test_the_command_line_reports_a_pending_provider_key(cli: BoundaryDaemon) -> None:
    d = cli
    made = d.client.post(
        "/api/v1/providers",
        json={
            "name": "gw",
            "protocol": "anthropic",
            "base_url": "https://gw.example.com/anthropic",
            "secret_value": "sk-cli-key-1",
        },
    )
    assert made.status_code == 201, made.text
    d.pending()  # the first key, just typed for this connection, is approved on sight
    ref = d.client.get(f"/api/v1/providers/{made.json()['uid']}").json()["secret_ref"]

    described = d.client.patch(
        f"/api/v1/providers/{made.json()['uid']}", json={"description": "gateway"}
    )
    assert described.status_code == 200, described.text
    assert d.pending() == []

    r = _runner.invoke(cli_app, ["secret", "set", ref, "--value", "sk-cli-key-2"])

    assert r.exit_code == 9, r.output
    assert "waiting for approval in the Coffer app" in r.stderr
    [replace] = [a for a in d.pending() if a["op"] == "replace_value"]
    assert replace["id"] in r.stderr
    assert d.value(ref) == "sk-cli-key-1"
