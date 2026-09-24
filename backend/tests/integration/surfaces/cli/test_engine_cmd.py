"""``coffer engine …`` — Coffer's own settings, driven from a terminal.

Booted against the REAL app (like ``test_memory_cmd.py``) rather than a
hand-wired subset, because what these scenarios claim is that the terminal and
the page are the same operation: the same route, the same service, the same
audit entry. A test that stood up its own service could not tell the
difference between that and a CLI writing somewhere else entirely.
"""

from __future__ import annotations

import json
import subprocess
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
    # The connection is addressed by the identity its creation minted, not by
    # the label the body named it with (ADR resource-identity-is-an-immutable-uid).
    uid = created.json()["uid"]
    assert http.post(f"/providers/{uid}/internal-default").status_code == 200

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


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="bound how long one call to Coffer's own model may take",
)
def test_engine_timeout_show_set_default(engine_cli_daemon):
    """The bound on one model call, from a terminal.

    The number is a property of the operator's endpoint, so an operator with
    only a terminal has to be able to raise it: against a gateway slower than
    the one the built-in bound was written for, every unattended pass defers
    its work while reporting success.
    """
    http = engine_cli_daemon

    # Nothing chosen: the terminal says which bound is actually in force rather
    # than printing a blank the reader has to interpret.
    r = _runner.invoke(cli_app, ["engine", "timeout", "show"])
    assert r.exit_code == 0, r.output
    assert "default (60s)" in r.output

    r = _runner.invoke(cli_app, ["engine", "timeout", "set", "180"])
    assert r.exit_code == 0, r.output
    assert "180" in r.output
    assert http.get("/internal-engine-config").json()["model_timeout_s"] == 180

    r = _runner.invoke(cli_app, ["engine", "timeout", "show", "--json"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output) == {"model_timeout_s": 180, "default_model_timeout_s": 60}

    # Out of range is refused by the same rule the page writes through (exit 6
    # — invalid input), not quietly rounded to something that fits.
    r = _runner.invoke(cli_app, ["engine", "timeout", "set", "1"])
    assert r.exit_code == 6, r.output
    assert http.get("/internal-engine-config").json()["model_timeout_s"] == 180

    r = _runner.invoke(cli_app, ["engine", "timeout", "default"])
    assert r.exit_code == 0, r.output
    assert http.get("/internal-engine-config").json()["model_timeout_s"] is None


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="speech-to-text runs on its own connection and its own model",
)
def test_engine_transcribe_model_show_set_clear(engine_cli_daemon):
    """The model Coffer hears speech with, set and given back up.

    Clearing it is an operating decision, not a failure: with no model the
    recording never leaves the machine and the agent is handed the audio file.
    """
    http = engine_cli_daemon

    r = _runner.invoke(cli_app, ["engine", "transcribe-model", "show"])
    assert r.exit_code == 0, r.output
    assert "no transcription model chosen" in r.output

    r = _runner.invoke(cli_app, ["engine", "transcribe-model", "set", "hears-things"])
    assert r.exit_code == 0, r.output
    assert "hears-things" in r.output
    assert http.get("/internal-engine-config").json()["transcribe_model"] == "hears-things"

    r = _runner.invoke(cli_app, ["engine", "transcribe-model", "show", "--json"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output) == {"transcribe_model": "hears-things"}

    r = _runner.invoke(cli_app, ["engine", "transcribe-model", "clear"])
    assert r.exit_code == 0, r.output
    assert http.get("/internal-engine-config").json()["transcribe_model"] is None


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="speech-to-text runs on its own connection and its own model",
)
def test_provider_transcribe_default_names_the_connection_speech_runs_on(engine_cli_daemon):
    """The other half of transcription, from the same terminal.

    Both halves or neither: the model is chosen on the engine's settings and
    the ENDPOINT on a connection, so a terminal that could only reach one of
    them could not turn transcription on at all.
    """
    http = engine_cli_daemon
    created = http.post(
        "/providers",
        json={
            "name": "hears",
            "protocol": "openai",
            "base_url": "https://gw/v1",
            "secret_value": "sk-secret-value",
        },
    )
    assert created.status_code == 201, created.text

    r = _runner.invoke(cli_app, ["provider", "transcribe-default", "hears"])
    assert r.exit_code == 0, r.output
    assert "hears" in r.output

    events = http.get("/audit", params={"event_type": "provider_transcribe_default_set"}).json()[
        "entries"
    ]
    assert events, "the CLI write recorded no provider_transcribe_default_set entry"
    assert events[0]["actor"] == "cli"
    assert events[0]["details"]["to"] == "hears"

    # A connection this vault does not have exits 4 (not found), the same way
    # `provider internal-default` does.
    r = _runner.invoke(cli_app, ["provider", "transcribe-default", "nope"])
    assert r.exit_code == 4, r.output


# --- the machine that may curate -------------------------------------------
#
# Curation is the one unattended pass that may run on exactly ONE machine, so
# its owner is a binding with the same four states a channel's has. What is
# asserted below is every one of them, and above all the two that a boolean
# cannot tell apart: an owner that names a machine still in the registry
# ("somewhere else") and one that names a machine nobody claims ("nowhere at
# all"). Only the second is a fault, and it is the state that silently stops
# curation on every machine at once.


def _machine_id(http) -> str:
    """This daemon's own machine id, from the surface the CLI reads it from."""
    return str(http.get("/sync/status").json()["machine_id"])


def _configure_remote(tmp_path) -> None:
    """Give this vault a remote, which is what makes a registry exist at all.

    ``GET /sync/machines`` reads ``machines/*.yaml`` out of the working tree
    (spec vault-sync: the registry is a derived view, not a table), and there
    is no working tree until a remote is configured. A real bare repository,
    because the route probes the one it is given.
    """
    bare = tmp_path / "curate-owner-remote.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(bare)], check=True, capture_output=True
    )
    r = _runner.invoke(cli_app, ["sync", "remote", "set", str(bare)])
    assert r.exit_code == 0, r.output


def _publish_machine(tmp_path, machine_id: str, name: str) -> None:
    """Put one machine in the registry by writing the file the registry IS.

    Each machine owns exactly ``machines/<id>.yaml`` and writes no other's, so
    a peer appearing is literally a file appearing — no round is needed to
    make one visible here.
    """
    machines = tmp_path / ".coffer" / "sync" / "machines"
    machines.mkdir(parents=True, exist_ok=True)
    (machines / f"{machine_id}.yaml").write_text(
        f"name: {name}\nos: Linux\nhostname: {name}\ncoffer_version: 0\nagents: []\n",
        encoding="utf-8",
    )


def test_curate_owner_show_on_a_vault_that_has_named_nobody(engine_cli_daemon):
    """No owner is not a fault: the pass runs wherever the setting is read.

    That is the right answer for a vault with one machine, and it is why
    curation can ship on without forcing a choice before there is anything to
    choose between.
    """
    r = _runner.invoke(cli_app, ["engine", "curate-owner", "show"])
    assert r.exit_code == 0, r.output
    assert "none" in r.output
    assert "wherever this vault is read" in r.output

    r = _runner.invoke(cli_app, ["engine", "curate-owner", "show", "--json"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["state"] == "unowned"


def test_curate_owner_set_defaults_to_this_machine(engine_cli_daemon):
    """No argument means "the machine I am typing on", like ``channel bind``."""
    http = engine_cli_daemon

    r = _runner.invoke(cli_app, ["engine", "curate-owner", "set"])
    assert r.exit_code == 0, r.output
    assert "this machine" in r.output

    # The same row the page writes, through the same route.
    assert http.get("/internal-engine-config").json()["curate_owner_machine_id"] == _machine_id(
        http
    )

    shown = _runner.invoke(cli_app, ["engine", "curate-owner", "show", "--json"])
    assert json.loads(shown.output)["state"] == "self"

    # ...and the audit entry a terminal leaves, stamped with the CLI as actor.
    # The event type is the engine singleton's own (``internal_engine_model_set``),
    # which is what every setting on this document records under today; the
    # DETAILS are what say which setting moved.
    events = http.get("/audit", params={"event_type": "internal_engine_model_set"}).json()[
        "entries"
    ]
    assert events, "the CLI write recorded no audit entry"
    assert events[0]["actor"] == "cli"
    assert events[0]["details"]["curate_owner_machine_id"] == _machine_id(http)


def test_curate_owner_set_takes_an_explicit_machine(engine_cli_daemon, tmp_path):
    """A named machine that the registry holds is "another machine", not a fault."""
    http = engine_cli_daemon
    _configure_remote(tmp_path)
    _publish_machine(tmp_path, _machine_id(http), "here")
    _publish_machine(tmp_path, "peer-machine-id", "laptop")
    # Stated so this scenario cannot pass for the reason the empty-registry one
    # below does: the registry really does hold both machines here.
    assert len(http.get("/sync/machines").json()["machines"]) == 2

    r = _runner.invoke(cli_app, ["engine", "curate-owner", "set", "peer-machine-id"])
    assert r.exit_code == 0, r.output
    assert "another machine" in r.output
    assert "NO machine" not in r.output

    shown = _runner.invoke(cli_app, ["engine", "curate-owner", "show", "--json"])
    assert json.loads(shown.output)["state"] == "other"


def test_curate_owner_reports_an_owner_no_machine_claims_as_a_fault(engine_cli_daemon, tmp_path):
    """The state that stops curation EVERYWHERE, called out as such.

    A registry that holds machines but not this owner is the retired-owner
    case: no timer anywhere will run the pass, and printing the id the way an
    ordinary remote owner is printed would read as "it is running elsewhere".
    """
    http = engine_cli_daemon
    _configure_remote(tmp_path)
    _publish_machine(tmp_path, _machine_id(http), "here")
    _publish_machine(tmp_path, "still-here", "laptop")

    # Written even though nobody claims it: the route does not validate against
    # the registry, deliberately. What changes is how it is read back.
    r = _runner.invoke(cli_app, ["engine", "curate-owner", "set", "retired-machine"])
    assert r.exit_code == 0, r.output
    assert "NO machine in this vault claims that id" in r.output
    assert "runs nowhere" in r.output
    # A fault a reader cannot act on is half a report.
    assert "curate-owner set" in r.output

    shown = _runner.invoke(cli_app, ["engine", "curate-owner", "show"])
    assert shown.exit_code == 0, shown.output
    assert "NO machine in this vault claims that id" in shown.output
    assert (
        json.loads(_runner.invoke(cli_app, ["engine", "curate-owner", "show", "--json"]).output)[
            "state"
        ]
        == "unknown"
    )


def test_an_empty_registry_is_never_reported_as_a_fault(engine_cli_daemon):
    """A vault that has never converged has no registry, and is not broken.

    This is the single-machine install — the commonest one there is. Reading
    "not in the registry" as "that machine is gone" would report a fault on
    every one of them, so an empty registry can only ever yield "another
    machine".
    """
    # No remote, so no working tree, so no registry at all — the state this
    # carve-out is about.
    assert engine_cli_daemon.get("/sync/machines").json()["machines"] == []

    r = _runner.invoke(cli_app, ["engine", "curate-owner", "set", "some-other-machine"])
    assert r.exit_code == 0, r.output
    assert "another machine" in r.output
    assert "NO machine" not in r.output

    shown = _runner.invoke(cli_app, ["engine", "curate-owner", "show", "--json"])
    assert json.loads(shown.output)["state"] == "other"


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="the command line shows, sets and clears the curation owner",
)
def test_curate_owner_show_set_clear(engine_cli_daemon):
    """show → set (this machine) → show --json → clear, read back over the route."""
    http = engine_cli_daemon
    here = _machine_id(http)

    r = _runner.invoke(cli_app, ["engine", "curate-owner", "show"])
    assert r.exit_code == 0, r.output
    assert r.output.strip() == "curation owner: none — the pass runs wherever this vault is read"

    r = _runner.invoke(cli_app, ["engine", "curate-owner", "set"])
    assert r.exit_code == 0, r.output
    assert r.output.strip() == f"curation owner: {here} (this machine)"
    assert http.get("/internal-engine-config").json()["curate_owner_machine_id"] == here

    r = _runner.invoke(cli_app, ["engine", "curate-owner", "show", "--json"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output) == {
        "curate_owner_machine_id": here,
        "state": "self",
        "this_machine_id": here,
    }

    r = _runner.invoke(cli_app, ["engine", "curate-owner", "clear"])
    assert r.exit_code == 0, r.output
    assert r.output.strip() == "curation owner: none — the pass runs wherever this vault is read"
    assert http.get("/internal-engine-config").json()["curate_owner_machine_id"] is None


def test_curate_owner_clear_returns_the_pass_to_every_machine(engine_cli_daemon):
    """Clearing is an operating decision, never a repair anything performs."""
    http = engine_cli_daemon
    assert _runner.invoke(cli_app, ["engine", "curate-owner", "set"]).exit_code == 0

    r = _runner.invoke(cli_app, ["engine", "curate-owner", "clear"])
    assert r.exit_code == 0, r.output
    assert "wherever this vault is read" in r.output
    assert http.get("/internal-engine-config").json()["curate_owner_machine_id"] is None


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="the bound and the speech-to-text model change one value at a time",
)
def test_engine_timeout_and_transcribe_model_set_leave_the_rest_of_the_row(engine_cli_daemon):
    """Each terminal write touches its own value only, and is audited like the route's."""
    http = engine_cli_daemon
    assert http.put("/internal-engine-config", json={"model": "brain"}).status_code == 200
    assert (
        http.put(
            "/internal-engine-config/upkeep", json={"pass": "distil", "enabled": False}
        ).status_code
        == 200
    )

    def _entries() -> list[dict]:
        return http.get(
            "/audit", params={"event_type": "internal_engine_model_set", "limit": 50}
        ).json()["entries"]

    before = len(_entries())

    r = _runner.invoke(cli_app, ["engine", "timeout", "set", "90"])
    assert r.exit_code == 0, r.output
    body = http.get("/internal-engine-config").json()
    assert body["model_timeout_s"] == 90
    assert body["transcribe_model"] is None
    assert body["model"] == "brain"
    assert body["upkeep"]["distil"]["enabled"] is False

    r = _runner.invoke(cli_app, ["engine", "transcribe-model", "set", "hears"])
    assert r.exit_code == 0, r.output
    body = http.get("/internal-engine-config").json()
    assert body["transcribe_model"] == "hears"
    assert body["model_timeout_s"] == 90
    assert body["model"] == "brain"
    assert body["upkeep"]["distil"]["enabled"] is False

    after = _entries()
    assert len(after) == before + 2
    assert {e["actor"] for e in after[: len(after) - before]} == {"cli"}


# --- upkeep runs: what is being rewritten right now --------------------------


@pytest.mark.acceptance(
    spec="resource-framework", scenario="the command line reads the passes in flight"
)
def test_upkeep_runs_names_every_pass_in_flight(engine_cli_daemon):
    """``engine upkeep runs`` is GET /upkeep/runs: each pass the daemon holds,
    by kind and target, oldest first."""
    from coffer.application.upkeep_runs import UPKEEP_RUNS

    assert UPKEEP_RUNS.claim("knowledge", "shopee") is True
    assert UPKEEP_RUNS.claim("memory", "coffer") is True
    try:
        as_json = _runner.invoke(cli_app, ["engine", "upkeep", "runs", "--json"])
        as_text = _runner.invoke(cli_app, ["engine", "upkeep", "runs"], env={"COLUMNS": "200"})
    finally:
        UPKEEP_RUNS.release("knowledge", "shopee")
        UPKEEP_RUNS.release("memory", "coffer")

    assert as_json.exit_code == 0, as_json.output
    runs = json.loads(as_json.output)["runs"]
    assert [(r["kind"], r["name"]) for r in runs] == [("knowledge", "shopee"), ("memory", "coffer")]
    assert all(r["started_at"] for r in runs)
    assert as_text.exit_code == 0, as_text.output
    shopee = next(line for line in as_text.output.splitlines() if "shopee" in line)
    coffer = next(line for line in as_text.output.splitlines() if "coffer" in line)
    assert "knowledge" in shopee and "memory" in coffer


@pytest.mark.acceptance(
    spec="resource-framework", scenario="the command line reads the passes in flight"
)
def test_upkeep_runs_says_so_when_nothing_is_running(engine_cli_daemon):
    as_json = _runner.invoke(cli_app, ["engine", "upkeep", "runs", "--json"])
    as_text = _runner.invoke(cli_app, ["engine", "upkeep", "runs"])

    assert as_json.exit_code == 0, as_json.output
    assert json.loads(as_json.output) == {"runs": []}
    assert as_text.exit_code == 0, as_text.output
    assert "no upkeep pass is running" in as_text.output
