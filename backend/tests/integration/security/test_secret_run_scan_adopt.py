"""`coffer run`, the plaintext scan and move, and the adoption at upgrade, against
a real in-process daemon over a throwaway HOME (spec credentials)."""

from __future__ import annotations

import json
import os
import pathlib
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from typer.testing import CliRunner

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


def _run(*argv: str) -> object:
    return _runner.invoke(cli_app, ["run", *argv])


# --- coffer run -----------------------------------------------------------------------


@pytest.mark.acceptance(spec="credentials", scenario="coffer run sets a secret only in the child")
def test_coffer_run_sets_a_secret_only_in_the_child(cli: BoundaryDaemon) -> None:
    d = cli
    d.store("secret/db-password", "correct-horse-battery")
    probe = (
        "import os; print('child-sees', os.environ.get('DB_PASSWORD') == 'correct-horse-battery')"
    )

    result = _runner.invoke(
        cli_app, ["run", "--secret", "db-password", "--", sys.executable, "-c", probe]
    )

    assert result.exit_code == 0, result.output
    assert "child-sees True" in result.output
    assert "DB_PASSWORD" not in os.environ
    [entry] = d.audit("secret_resolved")
    assert entry["details"]["name"] == "db-password"
    assert entry["details"]["argv0"] == sys.executable
    assert "correct-horse-battery" not in json.dumps(entry)


def test_coffer_run_resolves_env_file_references_and_named_variables(
    cli: BoundaryDaemon, tmp_path: pathlib.Path
) -> None:
    d = cli
    d.store("secret/api-token", "tok-0123456789")
    env_file = tmp_path / "app.env"
    env_file.write_text("MODE=test\nAPI=coffer://secret/api-token\n")
    probe = (
        "import os; v = 'tok-0123456789'; "
        "print(os.environ['MODE'], os.environ['API'] == v, os.environ['T2'] == v)"
    )

    result = _runner.invoke(
        cli_app,
        [
            "run",
            "--env-file",
            str(env_file),
            "--secret",
            "T2=api-token",
            "--",
            sys.executable,
            "-c",
            probe,
        ],
    )

    assert result.exit_code == 0, result.output
    assert "test True True" in result.output


@pytest.mark.acceptance(
    spec="credentials", scenario="coffer run masks the value in the child's output"
)
def test_coffer_run_masks_a_value_split_across_writes(cli: BoundaryDaemon) -> None:
    d = cli
    d.store("secret/db-password", "correct-horse-battery")
    probe = (
        "import os, sys, time; v = os.environ['DB_PASSWORD']; "
        "sys.stdout.write('pw=' + v[:7]); sys.stdout.flush(); time.sleep(0.2); "
        "sys.stdout.write(v[7:] + ' end\\n'); sys.stdout.flush(); "
        "sys.stderr.write('err ' + v + '\\n')"
    )

    result = _runner.invoke(
        cli_app, ["run", "--secret", "db-password", "--", sys.executable, "-c", probe]
    )

    assert result.exit_code == 0, result.output
    assert "pw=*** end" in result.output and "err ***" in result.output
    assert "correct-horse-battery" not in result.output


def test_coffer_run_passes_the_exit_status_through(cli: BoundaryDaemon) -> None:
    cli.store("secret/x-token", "value-long-enough")
    result = _runner.invoke(
        cli_app,
        ["run", "--secret", "x-token", "--", sys.executable, "-c", "raise SystemExit(7)"],
    )
    assert result.exit_code == 7


@pytest.mark.acceptance(
    spec="credentials", scenario="a resource's secret cannot be resolved by coffer run"
)
def test_a_resources_secret_cannot_be_resolved_by_coffer_run(cli: BoundaryDaemon) -> None:
    d = cli
    d.store("mcp_server/gh/TOKEN", "ghp_resource_token")
    d.register_stdio("gh", "server", {"TOKEN": "mcp_server/gh/TOKEN"})

    minted = d.client.post(
        "/api/v1/credentials/secrets/resolve",
        json={"names": ["mcp_server/gh/TOKEN"], "argv0": "env"},
    )
    unknown = d.client.post(
        "/api/v1/credentials/secrets/resolve", json={"names": ["TOKEN"], "argv0": "env"}
    )
    via_cli = _runner.invoke(cli_app, ["run", "--secret", "mcp_server/gh/TOKEN", "--", "env"])

    assert minted.status_code == 422 and unknown.status_code == 404
    assert via_cli.exit_code != 0
    for body in (minted.text, unknown.text, via_cli.output):
        assert "ghp_resource_token" not in body
    assert d.audit("secret_resolved") == []


# --- the plaintext scan and move ---------------------------------------------------------


def _plaintext(home: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    secrets = home / ".coffer" / "secrets"
    secrets.mkdir(parents=True)
    env = secrets / "db.env"
    env.write_text("# the test database\nDB_HOST=db.internal\nDB_PASSWORD=hunter2hunter2\n")
    env.chmod(0o600)
    skill = home / ".coffer" / "skills" / "deploy"
    (skill / "scripts").mkdir(parents=True)
    script = skill / "scripts" / "run.sh"
    script.write_text(
        '#!/bin/sh\nexport API_TOKEN="abcd1234efgh5678"\nsource ~/.coffer/secrets/db.env\n'
    )
    script.chmod(0o755)
    return env, script


@pytest.mark.acceptance(
    spec="credentials", scenario="a scan names plaintext secrets without their values"
)
def test_a_scan_names_plaintext_secrets_without_their_values(cli: BoundaryDaemon) -> None:
    _plaintext(cli.home)
    result = _runner.invoke(cli_app, ["credentials", "scan", "--json"])

    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    found = {(f["source"], f["key"], f["proposed_name"]) for f in body["findings"]}
    assert ("secrets_file", "DB_PASSWORD", "db.DB_PASSWORD") in found
    assert ("skill", "API_TOKEN", "deploy.api_token") in found
    # Every entry of a secrets file is a secret (ADR standalone-secrets-...).
    assert ("secrets_file", "DB_HOST", "db.DB_HOST") in found
    assert not any(
        f["source"] == "skill" and f["key"] == "API_TOKEN" and f["line"] != 2
        for f in body["findings"]
    )
    assert [m["skill"] for m in body["mentions"]] == ["deploy"]
    assert "hunter2hunter2" not in result.output and "abcd1234efgh5678" not in result.output


@pytest.mark.acceptance(
    spec="credentials", scenario="importing moves a value and leaves a reference"
)
def test_importing_moves_a_value_and_leaves_a_reference(cli: BoundaryDaemon) -> None:
    d = cli
    env, script = _plaintext(d.home)
    before = (env.read_text(), script.read_text())

    dry = _runner.invoke(cli_app, ["credentials", "import", "--dry-run"])
    assert dry.exit_code == 0, dry.output
    assert (env.read_text(), script.read_text()) == before
    assert d.value("secret/db.DB_PASSWORD") is None

    moved = _runner.invoke(cli_app, ["credentials", "import", "--yes"])

    assert moved.exit_code == 0, moved.output
    assert d.value("secret/db.DB_PASSWORD") == "hunter2hunter2"
    assert d.value("secret/deploy.api_token") == "abcd1234efgh5678"
    assert "DB_PASSWORD=coffer://secret/db.DB_PASSWORD" in env.read_text()
    assert env.read_text().startswith("# the test database\n")
    assert 'API_TOKEN="coffer://secret/deploy.api_token"' in script.read_text()
    assert (env.stat().st_mode & 0o777) == 0o600 and (script.stat().st_mode & 0o777) == 0o755
    assert "hunter2hunter2" not in moved.output
    names = sorted(e["details"]["name"] for e in d.audit("secret_imported"))
    assert names == ["db.DB_HOST", "db.DB_PASSWORD", "deploy.api_token"], names
    again = json.loads(_runner.invoke(cli_app, ["credentials", "scan", "--json"]).output)
    assert again["findings"] == []


# --- adoption at upgrade --------------------------------------------------------------------


@pytest.mark.acceptance(spec="credentials", scenario="bindings in use at upgrade keep working")
def test_bindings_in_use_at_upgrade_keep_working(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = prepare_home(tmp_path, monkeypatch)
    with running_daemon(tmp_path, db) as d:
        d.store("gh/token", "ghp_from_before")
        first = d.register_stdio("first", "server-one", {"TOKEN": "gh/token"})
        second = d.register_stdio("second", "server-two", {"TOKEN": "gh/token"})
    # Rewind to a vault from before the boundary: no bindings, no marker, and
    # a secret stored long ago.
    old = (datetime.now(tz=UTC) - timedelta(days=90)).isoformat()
    d.sql("DELETE FROM secret_bindings")
    d.sql("DELETE FROM secret_approvals")
    d.sql("DELETE FROM secret_boundary_settings")
    d.sql("UPDATE credentials SET created_at = ?", old)

    with running_daemon(tmp_path, db) as upgraded:
        assert upgraded.resolve_for(first) == {"TOKEN": "ghp_from_before"}
        assert upgraded.resolve_for(second) == {"TOKEN": "ghp_from_before"}
        assert upgraded.pending() == []
        adopted = upgraded.sql("SELECT COUNT(*) FROM secret_bindings")[0][0]
    assert adopted == 2

    with running_daemon(tmp_path, db) as again:
        assert again.sql("SELECT COUNT(*) FROM secret_bindings")[0][0] == 2
        third = again.register_stdio("third", "server-three", {"TOKEN": "gh/token"})
        assert again.pending(destination_uid=third["uid"]) != []
