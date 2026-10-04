"""The secret routes and commands against a real in-process daemon (spec secret).

Every test boots the whole app over a throwaway ``HOME`` and database, with the
process-wide keyring swapped for the shared in-memory backend — so the master
key, the store and the audit log are the real ones, and neither the developer's
``~/.coffer`` nor their OS keychain is ever touched.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.secret_composition import get_secret_store
from tests.fixtures.keyring import InMemoryKeyring, install_in_memory_keyring

TOKEN = "test-token-secrets-contract"


def _value(ref: str) -> str | None:
    """Read a value straight from the daemon's own store: no route returns one."""
    return get_secret_store().get(ref)


class _Daemon:
    def __init__(self, client: TestClient, keyring: InMemoryKeyring, home: pathlib.Path) -> None:
        self.client = client
        self.keyring = keyring
        self.home = home

    def audit(self, event_type: str) -> list[dict]:
        r = self.client.get("/api/v1/audit", params={"event_type": event_type, "limit": 500})
        assert r.status_code == 200, r.text
        return list(r.json()["entries"])

    def secret_audit(self) -> list[dict]:
        r = self.client.get("/api/v1/audit", params={"event_prefix": "secret", "limit": 500})
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


@pytest.mark.acceptance(
    spec="secret", scenario="storing a secret answers 204 and audits the ref only"
)
def test_storing_a_secret_answers_204_and_audits_the_ref_only(daemon: _Daemon) -> None:
    r = daemon.client.post("/api/v1/secrets", json={"ref": "gh/token", "value": "ghp_store_me_42"})
    assert r.status_code == 204, r.text
    assert daemon.client.get("/api/v1/secrets/gh/token/exists").json()["present"] is True

    entries = daemon.audit("secret_set")
    assert len(entries) == 1
    assert "gh/token" in json.dumps(entries[0]["details"])
    assert "ghp_store_me_42" not in json.dumps(entries[0])


@pytest.mark.acceptance(spec="secret", scenario="the presence probe records no audit entry")
def test_the_presence_probe_records_no_audit_entry(daemon: _Daemon) -> None:
    daemon.client.post("/api/v1/secrets", json={"ref": "gh/token", "value": "ghp_probe"})
    before = daemon.secret_audit()
    assert [e["event_type"] for e in before] == ["secret_set"]

    present = daemon.client.get("/api/v1/secrets/gh/token/exists")
    absent = daemon.client.get("/api/v1/secrets/never/stored/exists")
    assert present.status_code == 200 and present.json()["present"] is True
    assert absent.status_code == 200 and absent.json()["present"] is False

    assert daemon.secret_audit() == before


@pytest.mark.acceptance(spec="secret", scenario="secret audit events carry the ref only")
def test_secret_audit_events_carry_the_ref_only(daemon: _Daemon) -> None:
    secret = "sk-audit-must-never-carry-this"
    daemon.client.post("/api/v1/secrets", json={"ref": "svc/key", "value": secret})
    assert _value("svc/key") == secret
    assert daemon.client.delete("/api/v1/secrets/svc/key").status_code == 204

    for event in ("secret_set", "secret_deleted"):
        entries = daemon.audit(event)
        assert len(entries) == 1, event
        payload = json.dumps(entries[0])
        assert "svc/key" in json.dumps(entries[0]["details"]), event
        assert secret not in payload, event


@pytest.mark.acceptance(
    spec="secret",
    scenario="read and change the master key location from the API and the Settings card",
)
def test_read_and_change_the_master_key_location(daemon: _Daemon) -> None:
    daemon.client.post("/api/v1/secrets", json={"ref": "kept/key", "value": "v-survives"})

    r = daemon.client.get("/api/v1/settings/secrets")
    assert r.status_code == 200 and r.json()["master_key_storage"] == "file"

    moved = daemon.client.put("/api/v1/settings/secrets", json={"master_key_storage": "keychain"})
    assert moved.status_code == 200, moved.text
    assert moved.json()["master_key_storage"] == "keychain"
    assert daemon.client.get("/api/v1/settings/secrets").json()["master_key_storage"] == (
        "keychain"
    )
    # The key really moved: out of the file, into the (in-memory) keychain.
    assert not (daemon.home / "master.key").exists()
    assert any(daemon.keyring._data.values())

    assert _value("kept/key") == "v-survives"
