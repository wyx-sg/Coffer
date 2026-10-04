"""The plaintext scan and move over REST, against a real in-process daemon over a
throwaway HOME (spec secret "Move plaintext secret files into the store")."""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest

from tests.support.boundary_daemon import BoundaryDaemon, prepare_home, running_daemon


@pytest.fixture
def d(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryDaemon]:
    db = prepare_home(tmp_path, monkeypatch)
    with running_daemon(tmp_path, db) as daemon:
        yield daemon


def _plaintext(home: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    secrets = home / ".coffer" / "secrets"
    secrets.mkdir(parents=True)
    env = secrets / "db.env"
    env.write_text("# the test database\nDB_HOST=db.internal\nDB_PASSWORD=hunter2hunter2\n")
    env.chmod(0o600)
    skill = home / ".coffer" / "vault" / "skills" / "deploy"
    (skill / "scripts").mkdir(parents=True)
    script = skill / "scripts" / "run.sh"
    script.write_text(
        '#!/bin/sh\nexport API_TOKEN="abcd1234efgh5678"\nsource ~/.coffer/secrets/db.env\n'
    )
    script.chmod(0o755)
    return env, script


@pytest.mark.acceptance(
    spec="secret", scenario="a scan names plaintext secrets without their values"
)
def test_a_scan_names_plaintext_secrets_without_their_values(d: BoundaryDaemon) -> None:
    _plaintext(d.home)

    r = d.client.post("/api/v1/secrets/scan")

    assert r.status_code == 200, r.text
    body = r.json()
    found = {(f["source"], f["key"], f["proposed_name"]) for f in body["findings"]}
    assert ("secrets_file", "DB_PASSWORD", "db.DB_PASSWORD") in found
    assert ("skill", "API_TOKEN", "deploy.api_token") in found
    assert [m["skill"] for m in body["mentions"]] == ["deploy"]
    assert "hunter2hunter2" not in r.text and "abcd1234efgh5678" not in r.text


@pytest.mark.acceptance(spec="secret", scenario="importing moves a value and leaves a reference")
def test_importing_moves_a_value_and_leaves_a_reference(d: BoundaryDaemon) -> None:
    env, script = _plaintext(d.home)
    before = (env.read_text(), script.read_text())

    dry = d.client.post("/api/v1/secrets/import", json={"dry_run": True})
    assert dry.status_code == 200, dry.text
    assert (env.read_text(), script.read_text()) == before
    assert d.value("secret/db.DB_PASSWORD") is None

    moved = d.client.post("/api/v1/secrets/import", json={})

    assert moved.status_code == 200, moved.text
    assert d.value("secret/db.DB_PASSWORD") == "hunter2hunter2"
    assert d.value("secret/deploy.api_token") == "abcd1234efgh5678"
    assert "DB_PASSWORD=coffer://secret/db.DB_PASSWORD" in env.read_text()
    assert env.read_text().startswith("# the test database\n")
    assert 'API_TOKEN="coffer://secret/deploy.api_token"' in script.read_text()
    assert (env.stat().st_mode & 0o777) == 0o600 and (script.stat().st_mode & 0o777) == 0o755
    assert "hunter2hunter2" not in moved.text
    names = sorted(e["details"]["name"] for e in d.audit("secret_imported"))
    assert names == ["db.DB_HOST", "db.DB_PASSWORD", "deploy.api_token"], names
    again = d.client.post("/api/v1/secrets/scan").json()
    assert again["findings"] == []
