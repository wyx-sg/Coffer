"""The credential routes and commands against a real in-process daemon (spec credentials).

Every test boots the whole app over a throwaway ``HOME`` and database, with the
process-wide keyring swapped for the shared in-memory backend — so the master
key, the store and the audit log are the real ones, and neither the developer's
``~/.coffer`` nor their OS keychain is ever touched.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator
from typing import Any

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from tests.fixtures.keyring import InMemoryKeyring, install_in_memory_keyring

TOKEN = "test-token-credentials-contract"
_runner = CliRunner()


class _Daemon:
    def __init__(self, client: TestClient, keyring: InMemoryKeyring, home: pathlib.Path) -> None:
        self.client = client
        self.keyring = keyring
        self.home = home

    def audit(self, event_type: str) -> list[dict]:
        r = self.client.get("/api/v1/audit", params={"event_type": event_type, "limit": 500})
        assert r.status_code == 200, r.text
        return list(r.json()["entries"])

    def credential_audit(self) -> list[dict]:
        r = self.client.get("/api/v1/audit", params={"event_prefix": "credential", "limit": 500})
        assert r.status_code == 200, r.text
        return list(r.json()["entries"])


@pytest.fixture
def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[_Daemon]:
    keyring = install_in_memory_keyring(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59960")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59969")
    app = create_app()
    set_active_token(TOKEN)
    with TestClient(app, headers={"X-Coffer-Token": TOKEN}) as c:
        yield _Daemon(c, keyring, tmp_path)
    set_active_token(None)


class _CliTransport:
    """What ``client_or_exit`` hands a command: the daemon's own client, prefixed.

    The commands open it with ``with c:``. Entering a ``TestClient`` runs the
    app's lifespan, and leaving it runs shutdown — which would tear the daemon
    down under the test after every command — so entering and leaving here are
    no-ops and the one lifespan stays the fixture's.
    """

    def __init__(self, client: TestClient) -> None:
        self._client = client

    def __enter__(self) -> _CliTransport:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def get(self, path: str, **kw: Any) -> Any:
        return self._client.get(f"/api/v1{path}", **kw)

    def post(self, path: str, **kw: Any) -> Any:
        return self._client.post(f"/api/v1{path}", **kw)

    def put(self, path: str, **kw: Any) -> Any:
        return self._client.put(f"/api/v1{path}", **kw)

    def delete(self, path: str, **kw: Any) -> Any:
        return self._client.delete(f"/api/v1{path}", **kw)


@pytest.fixture
def cli(daemon: _Daemon, monkeypatch: pytest.MonkeyPatch) -> _Daemon:
    """Point every ``coffer`` command at the in-process daemon above."""
    transport = _CliTransport(daemon.client)
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (transport, object()))
    return daemon


@pytest.mark.acceptance(
    spec="credentials", scenario="storing a credential answers 204 and audits the ref only"
)
def test_storing_a_credential_answers_204_and_audits_the_ref_only(daemon: _Daemon) -> None:
    r = daemon.client.post(
        "/api/v1/credentials", json={"ref": "gh/token", "value": "ghp_store_me_42"}
    )
    assert r.status_code == 204, r.text
    assert daemon.client.get("/api/v1/credentials/gh/token/exists").json()["present"] is True

    entries = daemon.audit("credential_set")
    assert len(entries) == 1
    assert "gh/token" in json.dumps(entries[0]["details"])
    assert "ghp_store_me_42" not in json.dumps(entries[0])


@pytest.mark.acceptance(
    spec="credentials", scenario="reading a credential returns its value and audits the read"
)
def test_reading_a_credential_returns_its_value_and_audits_the_read(daemon: _Daemon) -> None:
    daemon.client.post("/api/v1/credentials", json={"ref": "gh/token", "value": "ghp_read_me_42"})
    assert daemon.audit("credential_read") == []

    r = daemon.client.get("/api/v1/credentials/gh/token")
    assert r.status_code == 200, r.text
    assert r.json()["value"] == "ghp_read_me_42"

    reads = daemon.audit("credential_read")
    assert len(reads) == 1
    assert "gh/token" in json.dumps(reads[0]["details"])
    assert "ghp_read_me_42" not in json.dumps(reads[0])

    assert daemon.client.get("/api/v1/credentials/never/stored").status_code == 404


@pytest.mark.acceptance(spec="credentials", scenario="the presence probe records no audit entry")
def test_the_presence_probe_records_no_audit_entry(daemon: _Daemon) -> None:
    daemon.client.post("/api/v1/credentials", json={"ref": "gh/token", "value": "ghp_probe"})
    before = daemon.credential_audit()
    assert [e["event_type"] for e in before] == ["credential_set"]

    present = daemon.client.get("/api/v1/credentials/gh/token/exists")
    absent = daemon.client.get("/api/v1/credentials/never/stored/exists")
    assert present.status_code == 200 and present.json()["present"] is True
    assert absent.status_code == 200 and absent.json()["present"] is False

    assert daemon.credential_audit() == before


@pytest.mark.acceptance(spec="credentials", scenario="credential audit events carry the ref only")
def test_credential_audit_events_carry_the_ref_only(daemon: _Daemon) -> None:
    secret = "sk-audit-must-never-carry-this"
    daemon.client.post("/api/v1/credentials", json={"ref": "svc/key", "value": secret})
    assert daemon.client.get("/api/v1/credentials/svc/key").json()["value"] == secret
    assert daemon.client.delete("/api/v1/credentials/svc/key").status_code == 204

    for event in ("credential_set", "credential_read", "credential_deleted"):
        entries = daemon.audit(event)
        assert len(entries) == 1, event
        payload = json.dumps(entries[0])
        assert "svc/key" in json.dumps(entries[0]["details"]), event
        assert secret not in payload, event


@pytest.mark.acceptance(
    spec="credentials",
    scenario="read and change the master key location from the API and the command line",
)
def test_read_and_change_the_master_key_location(cli: _Daemon) -> None:
    daemon = cli
    daemon.client.post("/api/v1/credentials", json={"ref": "kept/key", "value": "v-survives"})

    r = daemon.client.get("/api/v1/settings/credentials")
    assert r.status_code == 200 and r.json()["master_key_storage"] == "file"
    shown = _runner.invoke(cli_app, ["credentials", "storage"])
    assert shown.exit_code == 0, shown.output
    assert "file" in shown.output

    moved = daemon.client.put(
        "/api/v1/settings/credentials", json={"master_key_storage": "keychain"}
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["master_key_storage"] == "keychain"
    assert daemon.client.get("/api/v1/settings/credentials").json()["master_key_storage"] == (
        "keychain"
    )
    shown = _runner.invoke(cli_app, ["credentials", "storage"])
    assert shown.exit_code == 0, shown.output
    assert "keychain" in shown.output
    # The key really moved: out of the file, into the (in-memory) keychain.
    assert not (daemon.home / "master.key").exists()
    assert any(daemon.keyring._data.values())

    assert daemon.client.get("/api/v1/credentials/kept/key").json()["value"] == "v-survives"


@pytest.mark.acceptance(
    spec="credentials", scenario="the command line confirms a delete unless forced"
)
def test_the_command_line_confirms_a_delete_unless_forced(cli: _Daemon) -> None:
    daemon = cli
    daemon.client.post("/api/v1/credentials", json={"ref": "to/delete", "value": "v"})

    declined = _runner.invoke(cli_app, ["credentials", "delete", "to/delete"], input="n\n")
    assert declined.exit_code != 0
    assert daemon.client.get("/api/v1/credentials/to/delete/exists").json()["present"] is True

    forced = _runner.invoke(cli_app, ["credentials", "delete", "to/delete", "--force"])
    assert forced.exit_code == 0, forced.output
    assert "Delete credential" not in forced.output
    assert daemon.client.get("/api/v1/credentials/to/delete/exists").json()["present"] is False
