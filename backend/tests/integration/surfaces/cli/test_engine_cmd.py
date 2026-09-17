"""``coffer engine …`` — Coffer's own settings, driven from a terminal.

Booted against the REAL app (like ``test_memory_cmd.py``) rather than a
hand-wired subset, because what these scenarios claim is that the terminal and
the page are the same operation: the same route, the same service, the same
audit entry. A test that stood up its own service could not tell the
difference between that and a CLI writing somewhere else entirely.
"""

from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime as dt

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_runner = CliRunner()
_TOKEN = "test-token-engine-cli"


@pytest.fixture
def engine_cli_daemon(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59920")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59929")
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(tmp_path / "memory"))
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))

    app = create_app()
    set_active_token(_TOKEN)

    info = DaemonInfo(
        version=1,
        pid=12345,
        port=59920,
        token=_TOKEN,
        started_at=dt.now(tz=UTC),
        binary_path="/test",
    )

    client = TestClient(
        app,
        base_url="http://localhost/api/v1",
        # The actor the real CLI stamps every mutation with, so the audit entry
        # this test reads back is the one a terminal would really leave.
        headers={"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "cli"},
        raise_server_exceptions=False,
    )
    client.__enter__()

    class _PersistentClient:
        """The CLI closes its client after every command; the app's lifespan
        must outlive the whole test, so hand each command a shell over one
        long-lived client."""

        def __init__(self, inner: TestClient) -> None:
            self._inner = inner

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return None

        def __getattr__(self, item):  # type: ignore[no-untyped-def]
            return getattr(self._inner, item)

    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (_PersistentClient(client), info))
    yield client
    client.__exit__(None, None, None)
    set_active_token(None)


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="the command line shows and sets the engine model",
)
def test_engine_model_show_set_clear(engine_cli_daemon):
    """set → show → clear, with the route's own audit entry behind it."""
    http = engine_cli_daemon
    created = http.post(
        "/providers",
        json={
            "name": "acme",
            "protocol": "anthropic",
            "base_url": "https://gw/anthropic",
            "secret_value": "sk-secret-value",
        },
    )
    assert created.status_code == 201, created.text
    assert http.post("/providers/acme/internal-default").status_code == 200

    # Nothing chosen yet: the terminal says so in words rather than printing a
    # blank line the reader has to interpret.
    r = _runner.invoke(cli_app, ["engine", "model", "show"])
    assert r.exit_code == 0, r.output
    assert "no engine model chosen" in r.output

    r = _runner.invoke(cli_app, ["engine", "model", "set", "picked-model"])
    assert r.exit_code == 0, r.output
    assert "picked-model" in r.output

    r = _runner.invoke(cli_app, ["engine", "model", "show", "--json"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["model"] == "picked-model"

    # The route's effect, read back through the route: the same row the page
    # would have written.
    assert http.get("/internal-engine-config").json()["model"] == "picked-model"

    # ...and the same audit entry, stamped with the CLI as the actor.
    events = http.get("/audit", params={"event_type": "internal_engine_model_set"}).json()[
        "entries"
    ]
    assert events, "the CLI write recorded no internal_engine_model_set entry"
    assert events[0]["actor"] == "cli"
    assert events[0]["details"]["model"] == "picked-model"

    r = _runner.invoke(cli_app, ["engine", "model", "clear"])
    assert r.exit_code == 0, r.output
    assert http.get("/internal-engine-config").json()["model"] is None
    r = _runner.invoke(cli_app, ["engine", "model", "show"])
    assert "no engine model chosen" in r.output


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="the command line lists and changes each unattended pass",
)
def test_engine_upkeep_list_and_set(engine_cli_daemon):
    """The three passes Coffer runs unattended, from a terminal.

    This is the half an operator with only a terminal cannot do without: one
    of these passes rewrites their own knowledge files on a timer.
    """
    http = engine_cli_daemon

    # The listing is machine-readable and names all three parts of each pass —
    # the switch, the interval CHOSEN (none yet) and the default that runs
    # while none is.
    r = _runner.invoke(cli_app, ["engine", "upkeep", "list", "--json"])
    assert r.exit_code == 0, r.output
    upkeep = json.loads(r.output)
    assert set(upkeep) == {"aggregate", "distil", "curate"}
    # All three ship ON: `curate` derives the documents agents read from
    # sources it never rewrites (spec internal-engine), so the "one of them
    # is off" split the tidy pass justified is gone.
    assert [upkeep[k]["enabled"] for k in ("aggregate", "distil", "curate")] == [
        True,
        True,
        True,
    ]
    assert all(upkeep[k]["interval_s"] is None for k in upkeep)
    assert upkeep["aggregate"]["default_interval_s"] == 3600

    # The human-readable form names the default too, rather than leaving a
    # blank where a number belongs.
    r = _runner.invoke(cli_app, ["engine", "upkeep", "list"])
    assert r.exit_code == 0, r.output
    assert "aggregate" in r.output and "default" in r.output

    # One pass per invocation, each half on its own.
    r = _runner.invoke(cli_app, ["engine", "upkeep", "set", "curate", "--on"])
    assert r.exit_code == 0, r.output
    r = _runner.invoke(cli_app, ["engine", "upkeep", "set", "distil", "--interval", "900"])
    assert r.exit_code == 0, r.output

    after = http.get("/internal-engine-config").json()["upkeep"]
    assert after["curate"]["enabled"] is True
    assert after["distil"]["interval_s"] == 900
    # The passes neither command named are exactly as they stood.
    assert after["aggregate"] == {"enabled": True, "interval_s": None, "default_interval_s": 3600}
    assert after["curate"]["interval_s"] is None

    r = _runner.invoke(cli_app, ["engine", "upkeep", "set", "curate", "--off"])
    assert r.exit_code == 0, r.output
    assert http.get("/internal-engine-config").json()["upkeep"]["curate"]["enabled"] is False

    # Back to the pass's own default — which a null interval cannot express.
    r = _runner.invoke(cli_app, ["engine", "upkeep", "set", "distil", "--default-interval"])
    assert r.exit_code == 0, r.output
    assert http.get("/internal-engine-config").json()["upkeep"]["distil"]["interval_s"] is None


def test_engine_upkeep_set_refuses_what_the_route_refuses(engine_cli_daemon):
    """An unknown pass and an interval below the floor fail the same way here
    as over HTTP: refused (exit 6 — invalid input), not silently dropped."""
    r = _runner.invoke(cli_app, ["engine", "upkeep", "set", "vacuum", "--on"])
    assert r.exit_code == 6, r.output

    r = _runner.invoke(cli_app, ["engine", "upkeep", "set", "distil", "--interval", "5"])
    assert r.exit_code == 6, r.output


def test_engine_upkeep_set_needs_something_to_change(engine_cli_daemon):
    """Contradictory or empty flags are caught before a request is made."""
    r = _runner.invoke(cli_app, ["engine", "upkeep", "set", "curate"])
    assert r.exit_code == 2, r.output

    r = _runner.invoke(cli_app, ["engine", "upkeep", "set", "curate", "--on", "--off"])
    assert r.exit_code == 2, r.output

    r = _runner.invoke(
        cli_app,
        ["engine", "upkeep", "set", "curate", "--interval", "900", "--default-interval"],
    )
    assert r.exit_code == 2, r.output
