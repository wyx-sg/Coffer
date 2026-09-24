"""/api/v1/agents/{uid} answers only for agents, and keeps one agent per config dir.

Two guards of spec agent-registry, exercised over HTTP:

- "Register each agent as an agent resource identified by its uid": the per-agent
  routes take a uid, and a uid another kind minted (a skill's, here Coffer's own
  ``coffer-guide``) is not an agent — it is a 404, never a 422 from trying to
  read a skill's config as an agent's, and never a DELETE that removes the skill.
- "Allow one agent per name and per config directory": the rule holds on edit
  too — a PATCH moving an agent onto another agent's config dir is a 409.
"""

from __future__ import annotations

import pathlib

from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-agent-guards"


def _app(tmp_path: pathlib.Path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    return create_app()


def _client(app) -> TestClient:
    set_active_token(TOKEN)
    return TestClient(app, headers={"X-Coffer-Token": TOKEN})


def _guide_skill_uid(c: TestClient) -> str:
    """The uid of the skill Coffer seeds for itself at boot — a non-agent uid."""
    r = c.get("/api/v1/resources", params={"kind": "skill", "name": "coffer-guide"})
    assert r.status_code == 200, r.text
    matches = r.json()["resources"]
    assert len(matches) == 1, matches
    return matches[0]["uid"]


def _assert_not_found(r) -> None:
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_agent_routes_refuse_a_skill_uid(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59870)
    with _client(app) as c:
        skill_uid = _guide_skill_uid(c)

        _assert_not_found(c.get(f"/api/v1/agents/{skill_uid}"))
        _assert_not_found(c.patch(f"/api/v1/agents/{skill_uid}", json={"description": "x"}))
        _assert_not_found(c.get(f"/api/v1/agents/{skill_uid}/config-files"))
        _assert_not_found(c.delete(f"/api/v1/agents/{skill_uid}"))

        # The skill is untouched: still there, under the same uid and name.
        r = c.get(f"/api/v1/skills/{skill_uid}")
        assert r.status_code == 200, r.text
        assert r.json()["uid"] == skill_uid
        assert r.json()["name"] == "coffer-guide"
        assert c.get("/api/v1/agents").json()["items"] == []


def test_patch_config_dir_onto_another_agents_dir_is_409(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59880)
    first_dir = tmp_path / "cfg1"
    second_dir = tmp_path / "cfg2"
    first_dir.mkdir()
    second_dir.mkdir()
    with _client(app) as c:
        r1 = c.post(
            "/api/v1/agents",
            json={"type": "codex", "name": "one", "config_dir": str(first_dir)},
        )
        assert r1.status_code == 201, r1.text
        r2 = c.post(
            "/api/v1/agents",
            json={"type": "codex", "name": "two", "config_dir": str(second_dir)},
        )
        assert r2.status_code == 201, r2.text
        second_uid = r2.json()["uid"]

        r = c.patch(f"/api/v1/agents/{second_uid}", json={"config_dir": str(first_dir)})
        assert r.status_code == 409, r.text
        body = r.json()
        assert body["error"]["code"] == "AGENT_CONFIG_DIR_REGISTERED"
        assert "one" in body["error"]["message"]

        # Nothing moved: the second agent still lives in its own dir.
        after = c.get(f"/api/v1/agents/{second_uid}").json()
        assert after["config_dir"] == str(second_dir)

        # An agent re-saving its own dir is not a collision with itself.
        same = c.patch(
            f"/api/v1/agents/{second_uid}",
            json={"config_dir": str(second_dir), "description": "kept"},
        )
        assert same.status_code == 200, same.text
        assert same.json()["config_dir"] == str(second_dir)
        assert same.json()["description"] == "kept"
