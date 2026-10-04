"""The connection routes the web UI calls, end to end (spec provider-switching)."""

from __future__ import annotations

import pytest

from tests.integration.surfaces.http.test_provider_routes import (
    _activate,
    _agent_dir,
    _anthropic_body,
    _app,
    _client,
    _connection_of,
    _new,
    _register_agent,
)


def _audit(c, event_type: str) -> list[dict]:
    r = c.get("/api/v1/audit", params={"event_type": event_type})
    assert r.status_code == 200, r.text
    return r.json()["entries"]


def _flags(c) -> dict[str, bool]:
    rows = c.get("/api/v1/providers").json()["providers"]
    return {p["name"]: p["transcribe_default"] for p in rows}


@pytest.mark.acceptance(
    spec="provider-switching", scenario="the routes cover create, list, switch and revert"
)
def test_the_routes_create_list_switch_and_revert(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59841)
    with _client(app) as c:
        _register_agent(c, agent_type="claude_code", config_dir=_agent_dir(tmp_path, "cc"))
        uid = _new(c, _anthropic_body("acme"))

        listed = c.get("/api/v1/providers")
        assert listed.status_code == 200
        assert [p["name"] for p in listed.json()["providers"]] == ["acme"]

        assert _activate(c, uid).status_code == 200
        assert _connection_of(c, "claude_code") == uid

        assert c.post("/api/v1/providers/use-builtin/claude_code").status_code == 200
        assert _connection_of(c, "claude_code") is None


@pytest.mark.acceptance(
    spec="provider-switching", scenario="the speech-to-text connection is named over REST"
)
def test_the_transcribe_default_moves_to_the_named_connection(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59861)
    with _client(app) as c:
        a = _new(c, _anthropic_body("conn-a"))
        b = _new(c, _anthropic_body("conn-b"))
        assert c.post(f"/api/v1/providers/{a}/transcribe-default").status_code == 200

        assert c.post(f"/api/v1/providers/{b}/transcribe-default").status_code == 200
        flags = _flags(c)
        assert flags["conn-b"] is True
        assert flags["conn-a"] is False
        assert any(
            e["resource_name"] == "conn-b" for e in _audit(c, "provider_transcribe_default_set")
        )


@pytest.mark.acceptance(spec="provider-switching", scenario="rename a connection over REST")
def test_a_rename_keeps_the_uid_and_a_taken_name_is_refused(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59871)
    with _client(app) as c:
        uid = _new(c, _anthropic_body("acme"))
        _new(c, _anthropic_body("taken"))
        ref = c.get(f"/api/v1/providers/{uid}").json()["secret_ref"]

        renamed = c.patch(f"/api/v1/resources/{uid}", json={"name": "acme-eu"})
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["uid"] == uid and renamed.json()["name"] == "acme-eu"
        assert c.get(f"/api/v1/providers/{uid}").json()["secret_ref"] == ref
        assert [
            (e["details"]["from"], e["details"]["to"]) for e in _audit(c, "resource_renamed")
        ] == [("acme", "acme-eu")]

        clash = c.patch(f"/api/v1/resources/{uid}", json={"name": "taken"})
        assert clash.status_code == 409, clash.text
        assert clash.json()["error"]["code"] == "RESOURCE_ALREADY_EXISTS", clash.text
        assert c.get(f"/api/v1/resources/{uid}").json()["name"] == "acme-eu"
