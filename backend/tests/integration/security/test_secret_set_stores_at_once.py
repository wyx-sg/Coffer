"""`coffer secret set` stores a replacement at once, and a binding that waits exits 9, against
a real in-process daemon over a throwaway HOME (spec secret "Report a pending approval on the
command line by exiting")."""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import httpx
import pytest
from typer.testing import CliRunner

from coffer.surfaces.cli._client import render_http_error
from coffer.surfaces.cli._options import ExitCode
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


@pytest.mark.acceptance(
    spec="secret", scenario="storing a replacement value with the command line waits for nobody"
)
def test_storing_a_replacement_value_waits_for_nobody(cli: BoundaryDaemon) -> None:
    d = cli
    d.store("gh/token", "ghp_cli_value_1")
    d.register_stdio("first", "server-one", {"TOKEN": "gh/token"})
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
    ref = d.client.get(f"/api/v1/providers/{made.json()['uid']}").json()["secret_ref"]
    waiting_before = d.pending()

    first = _runner.invoke(cli_app, ["secret", "set", "gh/token", "--value", "ghp_cli_value_2"])
    second = _runner.invoke(cli_app, ["secret", "set", ref, "--value", "sk-cli-key-2"])

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert d.value("gh/token") == "ghp_cli_value_2" and d.value(ref) == "sk-cli-key-2"
    assert d.pending() == waiting_before


@pytest.mark.acceptance(
    spec="secret", scenario="a command whose change leaves a binding waiting exits 9"
)
def test_a_binding_that_waits_exits_9() -> None:
    request = httpx.Request("POST", "http://daemon/api/v1/resources")
    response = httpx.Response(
        409,
        request=request,
        json={"error": {"code": "SECRET_BINDING_PENDING", "message": "waiting for approval"}},
    )
    with pytest.raises(httpx.HTTPStatusError) as raised:
        response.raise_for_status()

    assert render_http_error(raised.value, verbose=False) == ExitCode.APPROVAL_PENDING
