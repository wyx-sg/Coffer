"""Provider-switching requirements exercised end to end over HTTP (spec provider-switching).

Each test boots the whole app over a throwaway ``HOME`` and database, with the
process-wide keyring swapped for the shared in-memory backend, so the master
key, the vault, the audit log and the agents' native config files are all real
— and none of them is the developer's.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from starlette.testclient import TestClient

from coffer.domain.audit import AuditEventType
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from tests.fixtures.keyring import install_in_memory_keyring

TOKEN = "test-token-provider-requirements"


@pytest.fixture
def env(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    install_in_memory_keyring(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59940")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59949")
    return tmp_path


@contextmanager
def _daemon() -> Iterator[TestClient]:
    """One daemon lifetime: startup (including the boot sweeps), then shutdown."""
    app = create_app()
    set_active_token(TOKEN)
    try:
        with TestClient(app, headers={"X-Coffer-Token": TOKEN}) as c:
            yield c
    finally:
        set_active_token(None)


def _new(c: TestClient, body: dict) -> str:
    r = c.post("/api/v1/providers", json=body)
    assert r.status_code == 201, r.text
    return str(r.json()["uid"])


def _anthropic(name: str, secret: str = "sk-first") -> dict:
    return {
        "name": name,
        "protocol": "anthropic",
        "base_url": "https://gw/anthropic",
        "secret_value": secret,
    }


def _register_agent(c: TestClient, agent_type: str, name: str, config_dir: pathlib.Path) -> str:
    config_dir.mkdir(parents=True, exist_ok=True)
    r = c.post(
        "/api/v1/agents", json={"type": agent_type, "name": name, "config_dir": str(config_dir)}
    )
    assert r.status_code == 201, r.text
    return str(r.json()["uid"])


def _audit(c: TestClient, event_type: str) -> list[dict]:
    r = c.get("/api/v1/audit", params={"event_type": event_type, "limit": 500})
    assert r.status_code == 200, r.text
    return list(r.json()["entries"])


@pytest.mark.acceptance(
    spec="provider-switching", scenario="a connection is a provider resource addressed by its uid"
)
def test_a_connection_is_a_provider_resource_addressed_by_its_uid(env: pathlib.Path) -> None:
    with _daemon() as c:
        first = c.post("/api/v1/providers", json=_anthropic("acme"))
        assert first.status_code == 201, first.text
        uid = first.json()["uid"]
        assert uid != "acme" and len(uid) == 32

        row = c.get(f"/api/v1/resources/{uid}")
        assert row.status_code == 200, row.text
        assert row.json()["kind"] == "provider"
        assert row.json()["name"] == "acme"
        assert row.json()["uid"] == uid

        dup = c.post("/api/v1/providers", json=_anthropic("acme", secret="sk-other"))
        assert dup.status_code == 409, dup.text
        assert "RESOURCE_ALREADY_EXISTS" in dup.text

        listed = c.get("/api/v1/providers").json()["providers"]
        assert [p["uid"] for p in listed if p["name"] == "acme"] == [uid]


@pytest.mark.acceptance(
    spec="provider-switching", scenario="rotate a connection's secret without changing its ref"
)
def test_rotate_a_connections_secret_without_changing_its_ref(env: pathlib.Path) -> None:
    with _daemon() as c:
        uid = _new(c, _anthropic("acme", secret="sk-before-rotation"))
        ref = c.get(f"/api/v1/providers/{uid}").json()["credential_ref"]
        assert c.get(f"/api/v1/providers/{uid}/key").json()["value"] == "sk-before-rotation"

        r = c.patch(f"/api/v1/providers/{uid}", json={"secret_value": "sk-after-rotation"})
        assert r.status_code == 200, r.text
        assert r.json()["credential_ref"] == ref
        assert "sk-after-rotation" not in r.text

        assert c.get(f"/api/v1/providers/{uid}").json()["credential_ref"] == ref
        assert c.get(f"/api/v1/credentials/{ref}").json()["value"] == "sk-after-rotation"
        assert c.get(f"/api/v1/providers/{uid}/key").json()["value"] == "sk-after-rotation"


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="boot clears an active flag the agent's config does not carry",
)
def test_boot_clears_an_active_flag_the_agents_config_does_not_carry(env: pathlib.Path) -> None:
    cfg = env / "cc-config"
    with _daemon() as c:
        _register_agent(c, "claude_code", "cc", cfg)
        uid = _new(c, _anthropic("acme"))
        act = c.post(f"/api/v1/providers/{uid}/activate")
        assert act.status_code == 200, act.text
        assert c.get(f"/api/v1/providers/{uid}").json()["is_active"] is True

    # While the daemon was down, something else rewrote the agent's config —
    # it carries none of Coffer's keys any more.
    settings = cfg / "settings.json"
    user_owned = json.dumps({"theme": "dark", "env": {"OTHER": "1"}}, indent=2) + "\n"
    settings.write_text(user_owned, encoding="utf-8")

    with _daemon() as c:
        assert c.get(f"/api/v1/providers/{uid}").json()["is_active"] is False

    # The heal corrects Coffer's own record only: nothing was written back.
    assert settings.read_text(encoding="utf-8") == user_owned


@pytest.mark.acceptance(
    spec="provider-switching", scenario="each provider operation records its own audit event"
)
def test_each_provider_operation_records_its_own_audit_event(env: pathlib.Path) -> None:
    with _daemon() as c:
        _register_agent(c, "claude_code", "cc", env / "cc-config")
        acme = _new(c, _anthropic("acme"))
        other = _new(
            c,
            {
                "name": "other",
                "protocol": "openai",
                "base_url": "https://gw/v1",
                "secret_value": "sk-other",
            },
        )

        assert c.post(f"/api/v1/providers/{acme}/activate").status_code == 200
        assert c.post(f"/api/v1/providers/{acme}/internal-default").status_code == 200
        assert c.post(f"/api/v1/providers/{other}/transcribe-default").status_code == 200

        switched = _audit(c, "provider_switched")
        assert len(switched) == 1
        assert switched[0]["details"]["to"] == "acme"

        internal = _audit(c, "provider_internal_default_set")
        assert len(internal) == 1
        assert "acme" in json.dumps(internal[0])

        transcribe = _audit(c, "provider_transcribe_default_set")
        assert len(transcribe) == 1
        assert transcribe[0]["details"]["to"] == "other"

    values = {e.value for e in AuditEventType}
    assert {
        "provider_switched",
        "provider_internal_default_set",
        "provider_transcribe_default_set",
        "provider_projection_refused",
    } <= values


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="marking a speech-to-text default moves only its own flag",
)
def test_marking_a_speech_to_text_default_moves_only_its_own_flag(env: pathlib.Path) -> None:
    with _daemon() as c:
        a = _new(c, _anthropic("a"))
        b = _new(
            c,
            {"name": "b", "protocol": "openai", "base_url": "https://gw/v1", "secret_value": "sk"},
        )
        assert c.post(f"/api/v1/providers/{a}/internal-default").status_code == 200
        assert c.post(f"/api/v1/providers/{a}/transcribe-default").status_code == 200

        r = c.post(f"/api/v1/providers/{b}/transcribe-default")
        assert r.status_code == 200, r.text
        assert r.json()["transcribe_default"] is True

        got_a = c.get(f"/api/v1/providers/{a}").json()
        got_b = c.get(f"/api/v1/providers/{b}").json()
        assert (got_a["internal_default"], got_a["transcribe_default"]) == (True, False)
        assert (got_b["internal_default"], got_b["transcribe_default"]) == (False, True)

        moves = [e["details"] for e in _audit(c, "provider_transcribe_default_set")]
        assert {"from": "a", "to": "b"} in moves
