"""``coffer config`` over the engine's settings row — each scenario of spec
internal-engine that a terminal drives.

Booted against the REAL app (``_real_app``) rather than a hand-wired subset,
because what these scenarios claim is that the terminal and Settings → Coffer's
model are the same operation: the same route, the same service, the same audit
entry. A test that stood up its own service could not tell that apart from a
CLI writing somewhere else entirely.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
from collections.abc import Iterator
from typing import Any

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

from coffer.domain.vault.writers import WRITER_DAEMON, CommitMeta
from coffer.infrastructure.vault.instance import vault_writer
from coffer.surfaces.cli.main import app as cli_app

from ._real_app import audit, boot, extract_json

_runner = CliRunner()


@pytest.fixture
def daemon(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    yield from boot(tmp_path, monkeypatch)


def _run(*args: str) -> Any:
    return _runner.invoke(cli_app, list(args), env={"COLUMNS": "250"})


def _row(http: TestClient) -> dict[str, Any]:
    body: dict[str, Any] = http.get("/internal-engine-config").json()
    return body


def _internal_default(http: TestClient, name: str) -> None:
    created = http.post(
        "/providers",
        json={
            "name": name,
            "protocol": "anthropic",
            "base_url": f"https://{name}.example/anthropic",
            "secret_value": "sk-secret-value",
        },
    )
    assert created.status_code == 201, created.text
    uid = created.json()["uid"]
    assert http.post(f"/providers/{uid}/internal-default").status_code == 200


# --- engine.model ---------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="internal-engine", scenario="the command line shows and sets the engine model"
)
def test_engine_model_is_set_read_and_unset_with_the_routes_audit_entry(
    daemon: TestClient,
) -> None:
    _internal_default(daemon, "acme")

    # Nothing chosen yet: said in words, not a blank line to interpret.
    assert "no engine model chosen" in _run("config", "get", "engine.model").output

    r = _run("config", "set", "engine.model", "picked-model")
    assert r.exit_code == 0, r.output
    assert "picked-model" in r.output
    assert _row(daemon)["model"] == "picked-model"
    got = _run("config", "get", "engine.model", "--json")
    assert extract_json(got.output)["value"] == "picked-model"

    events = audit(daemon, "internal_engine_model_set")
    assert events, "the CLI write recorded no internal_engine_model_set entry"
    assert events[0]["actor"] == "cli"
    assert events[0]["details"]["model"] == "picked-model"

    r = _run("config", "unset", "engine.model")
    assert r.exit_code == 0, r.output
    assert _row(daemon)["model"] is None
    assert "no engine model chosen" in _run("config", "get", "engine.model").output


# --- engine.upkeep.<pass>.* -------------------------------------------------------------


@pytest.mark.acceptance(
    spec="internal-engine", scenario="the command line lists and changes each unattended pass"
)
def test_each_unattended_pass_is_listed_and_changed_one_value_at_a_time(
    daemon: TestClient,
) -> None:
    listed = _run("config", "list", "engine.upkeep.", "--json")
    assert listed.exit_code == 0, listed.output
    rows = {r["key"]: r for r in extract_json(listed.output)["settings"]}
    for name in ("aggregate", "distil", "curate"):
        # The switch, the chosen interval (none yet) and the default that runs
        # while none is chosen.
        assert rows[f"engine.upkeep.{name}.enabled"]["value"] is True
        assert rows[f"engine.upkeep.{name}.interval"]["value"] is None
        assert rows[f"engine.upkeep.{name}.interval"]["default"] > 0
    assert rows["engine.upkeep.aggregate.interval"]["default"] == 3600

    assert _run("config", "set", "engine.upkeep.curate.enabled", "off").exit_code == 0
    assert _run("config", "set", "engine.upkeep.distil.interval", "900").exit_code == 0
    after = _row(daemon)["upkeep"]
    assert after["curate"]["enabled"] is False and after["curate"]["interval_s"] is None
    assert after["distil"]["enabled"] is True and after["distil"]["interval_s"] == 900
    # The pass neither command named is exactly as it stood.
    assert {k: after["aggregate"][k] for k in ("enabled", "interval_s", "default_interval_s")} == {
        "enabled": True,
        "interval_s": None,
        "default_interval_s": 3600,
    }

    assert _run("config", "unset", "engine.upkeep.distil.interval").exit_code == 0
    assert _row(daemon)["upkeep"]["distil"]["interval_s"] is None

    # Below the floor: the route's own refusal (exit 6 — invalid input).
    below = _run("config", "set", "engine.upkeep.distil.interval", "5")
    assert below.exit_code == 6, below.output
    # A pass Coffer does not run is an unknown key, refused before any route.
    unknown = _run("config", "set", "engine.upkeep.vacuum.enabled", "on")
    assert unknown.exit_code == 4, unknown.output
    assert _row(daemon)["upkeep"]["distil"]["interval_s"] is None


# --- engine.timeout ------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="internal-engine", scenario="bound how long one call to Coffer's own model may take"
)
def test_the_bound_on_one_model_call_is_read_set_and_returned_to_default(
    daemon: TestClient,
) -> None:
    first = _run("config", "get", "engine.timeout")
    assert first.exit_code == 0, first.output
    assert "default (60s)" in first.output

    r = _run("config", "set", "engine.timeout", "180")
    assert r.exit_code == 0, r.output
    assert _row(daemon)["model_timeout_s"] == 180
    body = extract_json(_run("config", "get", "engine.timeout", "--json").output)
    assert body["value"] == 180 and body["default"] == 60

    # Out of range is refused by the rule the page writes through, not rounded.
    refused = _run("config", "set", "engine.timeout", "1")
    assert refused.exit_code == 6, refused.output
    assert _row(daemon)["model_timeout_s"] == 180

    assert _run("config", "unset", "engine.timeout").exit_code == 0
    assert _row(daemon)["model_timeout_s"] is None


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="the bound and the speech-to-text model change one value at a time",
)
def test_the_bound_and_the_speech_model_leave_the_rest_of_the_row(daemon: TestClient) -> None:
    assert daemon.put("/internal-engine-config", json={"model": "brain"}).status_code == 200
    switched_off = daemon.put(
        "/internal-engine-config/upkeep", json={"pass": "distil", "enabled": False}
    )
    assert switched_off.status_code == 200
    before = len(audit(daemon, "internal_engine_model_set"))

    assert _run("config", "set", "engine.timeout", "90").exit_code == 0
    row = _row(daemon)
    assert (row["model_timeout_s"], row["transcribe_model"], row["model"]) == (90, None, "brain")
    assert row["upkeep"]["distil"]["enabled"] is False

    assert _run("config", "set", "transcribe.model", "hears").exit_code == 0
    row = _row(daemon)
    assert (row["transcribe_model"], row["model_timeout_s"], row["model"]) == ("hears", 90, "brain")
    assert row["upkeep"]["distil"]["enabled"] is False

    after = audit(daemon, "internal_engine_model_set")
    assert len(after) == before + 2
    assert {e["actor"] for e in after[: len(after) - before]} == {"cli"}

    assert _run("config", "unset", "transcribe.model").exit_code == 0
    assert _row(daemon)["transcribe_model"] is None


# --- engine.curate_owner -------------------------------------------------------------
#
# Curation may run on exactly ONE machine, so its owner has the four states a
# channel binding has. Only "an owner no machine claims" is a fault, and it is
# the state that silently stops curation everywhere at once.


def _machine_id(http: TestClient) -> str:
    return str(http.get("/daemon/status").json()["machine_id"])


@pytest.mark.acceptance(
    spec="internal-engine", scenario="the command line shows, sets and clears the curation owner"
)
def test_curation_owner_is_shown_set_and_cleared(daemon: TestClient) -> None:
    here = _machine_id(daemon)
    unowned = "curation owner: none — the pass runs wherever this vault is read"

    r = _run("config", "get", "engine.curate_owner")
    assert r.exit_code == 0, r.output
    assert r.output.strip() == unowned

    r = _run("config", "set", "engine.curate_owner", "this")
    assert r.exit_code == 0, r.output
    assert r.output.strip() == f"curation owner: {here} (this machine)"
    assert _row(daemon)["curate_owner_machine_id"] == here

    body = extract_json(_run("config", "get", "engine.curate_owner", "--json").output)
    assert body["curate_owner_machine_id"] == here
    assert body["state"] == "self" and body["this_machine_id"] == here

    r = _run("config", "unset", "engine.curate_owner")
    assert r.exit_code == 0, r.output
    assert r.output.strip() == unowned
    assert _row(daemon)["curate_owner_machine_id"] is None


def _publish_machines(http: TestClient, home: pathlib.Path, *extra: str) -> None:
    """Give the vault a remote and put this machine plus ``extra`` in the
    registry, by committing the descriptor files the registry is."""
    bare = home / "curate-owner-remote.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(bare)], check=True, capture_output=True
    )
    r = _run("sync", "remote", "set", str(bare))
    assert r.exit_code == 0, r.output
    meta = CommitMeta(writer=WRITER_DAEMON, operation="update", summary="Described machines")
    with vault_writer().begin(meta) as txn:
        for machine_id in (_machine_id(http), *extra):
            doc = {"machine_id": machine_id, "format_version": 1, "name": machine_id, "agents": []}
            txn.write(f"machines/{machine_id}.json", (json.dumps(doc) + "\n").encode())


def test_an_owner_no_machine_claims_is_reported_as_a_fault(
    daemon: TestClient, tmp_path: pathlib.Path
) -> None:
    _publish_machines(daemon, tmp_path, "still-here")

    other = _run("config", "set", "engine.curate_owner", "still-here")
    assert other.exit_code == 0, other.output
    assert "another machine" in other.output and "NO machine" not in other.output

    gone = _run("config", "set", "engine.curate_owner", "retired-machine")
    assert gone.exit_code == 0, gone.output
    assert "NO machine in this vault claims that id" in gone.output
    assert "runs nowhere" in gone.output
    # A fault a reader cannot act on is half a report.
    assert "coffer config set engine.curate_owner this" in gone.output
    body = extract_json(_run("config", "get", "engine.curate_owner", "--json").output)
    assert body["state"] == "unknown"


def test_an_empty_registry_is_never_reported_as_a_fault(daemon: TestClient) -> None:
    """A vault that has never converged has no registry, and is not broken."""
    r = _run("config", "set", "engine.curate_owner", "some-other-machine")
    assert r.exit_code == 0, r.output
    assert "another machine" in r.output and "NO machine" not in r.output
