"""End-to-end HTTP coverage for /api/v1/agents/* (spec 004-agent-registry)."""

from __future__ import annotations

import pathlib

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-002"


def _app(tmp_path: pathlib.Path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    return create_app()


def _client(app) -> TestClient:
    set_active_token(TOKEN)
    return TestClient(app, headers={"X-Coffer-Token": TOKEN})


def _post_codex(c: TestClient, name: str, skill_dir: pathlib.Path):
    """Helper to register one codex agent — keeps line widths reasonable."""
    return c.post(
        "/api/v1/agents",
        json={"type": "codex", "name": name, "skill_dir": str(skill_dir)},
    )


# ---------------------------------------------------------------------------
# Per-verb tests (split from the former mega CRUD test — TEST25-007 / TEST25-101)
# ---------------------------------------------------------------------------


def test_agent_list_empty(tmp_path, monkeypatch):
    """List with no markers + no registrations returns 200 + empty items."""
    app = _app(tmp_path, monkeypatch, 59600)
    with _client(app) as c:
        r = c.get("/api/v1/agents")
        assert r.status_code == 200, r.text
        assert r.json()["items"] == []


def test_agent_register_post(tmp_path, monkeypatch):
    """POST /agents creates an agent from the request body."""
    app = _app(tmp_path, monkeypatch, 59601)
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    with _client(app) as c:
        r = c.post(
            "/api/v1/agents",
            json={
                "type": "codex",
                "name": "cur",
                "skill_dir": str(skill_dir),
                "description": "manual",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["name"] == "cur"
        assert body["type"] == "codex"
        assert "auto_detected" not in body


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="register an agent without an explicit name"
)
def test_agent_register_without_name_defaults_to_type(tmp_path, monkeypatch):
    """POST /agents with no name derives a stable default from the type
    (mirrors discovery's suggested name: claude_code -> claude-code)."""
    app = _app(tmp_path, monkeypatch, 59607)
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    with _client(app) as c:
        r = c.post(
            "/api/v1/agents",
            json={"type": "claude_code", "skill_dir": str(skill_dir)},
        )
        assert r.status_code == 201, r.text
        assert r.json()["name"] == "claude-code"


def test_agent_get_one(tmp_path, monkeypatch):
    """GET /agents/{name} returns the persisted skill_dir."""
    app = _app(tmp_path, monkeypatch, 59602)
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    with _client(app) as c:
        r = c.post(
            "/api/v1/agents",
            json={"type": "codex", "name": "cur", "skill_dir": str(skill_dir)},
        )
        assert r.status_code == 201, r.text
        r = c.get("/api/v1/agents/cur")
        assert r.status_code == 200
        assert r.json()["skill_dir"] == str(skill_dir)


def test_agent_list_after_register(tmp_path, monkeypatch):
    """A freshly registered agent appears in the list."""
    app = _app(tmp_path, monkeypatch, 59603)
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    with _client(app) as c:
        _post_codex(c, "cur", skill_dir)
        r = c.get("/api/v1/agents")
        assert r.status_code == 200
        assert any(a["name"] == "cur" for a in r.json()["items"])


def test_agent_patch_skill_dir(tmp_path, monkeypatch):
    """PATCH updates skill_dir (agents have no enable/disable concept)."""
    app = _app(tmp_path, monkeypatch, 59604)
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    new_dir = tmp_path / "skills2"
    new_dir.mkdir()
    with _client(app) as c:
        _post_codex(c, "cur", skill_dir)
        r = c.patch(
            "/api/v1/agents/cur",
            json={"skill_dir": str(new_dir)},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["skill_dir"] == str(new_dir)
        assert "enabled" not in body


def test_agent_candidates_get(tmp_path, monkeypatch):
    """GET /agents/candidates is callable + returns 200 even with no markers."""
    app = _app(tmp_path, monkeypatch, 59605)
    with _client(app) as c:
        r = c.get("/api/v1/agents/candidates")
        assert r.status_code == 200, r.text
        assert "candidates" in r.json()


def test_agent_delete_then_404(tmp_path, monkeypatch):
    """DELETE removes the agent; subsequent GET yields 404."""
    app = _app(tmp_path, monkeypatch, 59606)
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    with _client(app) as c:
        _post_codex(c, "cur", skill_dir)
        r = c.delete("/api/v1/agents/cur")
        assert r.status_code == 204
        r = c.get("/api/v1/agents/cur")
        assert r.status_code == 404


def test_patch_description_only_preserves_skill_dir(tmp_path, monkeypatch):
    """Regression: a PATCH that omits skill_dir must not wipe the override.

    `AgentPatch.skill_dir` defaults to None, so "field absent" and "field
    set to null" look identical on the model — the route must use
    `model_fields_set` to tell them apart.
    """
    app = _app(tmp_path, monkeypatch, 59610)
    skill_dir = tmp_path / "custom-skills"
    skill_dir.mkdir()

    with _client(app) as c:
        r = c.post(
            "/api/v1/agents",
            json={
                "type": "codex",
                "name": "cur",
                "skill_dir": str(skill_dir),
                "description": "before",
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["skill_dir_override"] == str(skill_dir)

        # PATCH only the description — skill_dir is absent from the body.
        r = c.patch("/api/v1/agents/cur", json={"description": "after"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["description"] == "after"
        # The custom skill_dir override must survive a description-only PATCH.
        assert body["skill_dir_override"] == str(skill_dir)
        assert body["skill_dir"] == str(skill_dir)

        # And it must still be persisted on a fresh read.
        r = c.get("/api/v1/agents/cur")
        assert r.json()["skill_dir_override"] == str(skill_dir)


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="discover installed agents as candidates"
)
def test_candidates_endpoint_reports_marker_present_agents(tmp_path, monkeypatch):
    """GET /candidates reports installed agents as candidates and registers nothing."""
    app = _app(tmp_path, monkeypatch, 59620)
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".claude").mkdir()

    with _client(app) as c:
        r = c.get("/api/v1/agents/candidates")
        assert r.status_code == 200, r.text
        cands = r.json()["candidates"]
        types = {c["type"] for c in cands}
        assert "codex" in types
        assert "claude_code" in types
        # Each candidate carries the fields the UI needs to confirm an add.
        for c_ in cands:
            assert c_["display_name"]
            assert c_["config_dir"]
            assert c_["default_skill_dir"]
            assert c_["suggested_name"]

        # Discovery is read-only — nothing was registered.
        assert c.get("/api/v1/agents").json()["items"] == []


# ---------------------------------------------------------------------------
# TEST25-106 — HTTP error response envelopes (400/404/409/422)
# ---------------------------------------------------------------------------


def test_error_404_not_found(tmp_path, monkeypatch):
    """GET an unknown agent name yields a 404 error envelope."""
    app = _app(tmp_path, monkeypatch, 59630)
    with _client(app) as c:
        r = c.get("/api/v1/agents/ghost")
        assert r.status_code == 404
        body = r.json()
        assert "error" in body
        assert body["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_error_409_duplicate_name(tmp_path, monkeypatch):
    """Registering the same name twice yields 409 RESOURCE_ALREADY_EXISTS."""
    app = _app(tmp_path, monkeypatch, 59631)
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    with _client(app) as c:
        r = c.post(
            "/api/v1/agents",
            json={"type": "codex", "name": "dup", "skill_dir": str(skill_dir)},
        )
        assert r.status_code == 201, r.text
        r = c.post(
            "/api/v1/agents",
            json={"type": "claude_code", "name": "dup", "skill_dir": str(skill_dir)},
        )
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "RESOURCE_ALREADY_EXISTS"


def test_error_422_skill_dir_not_writable(tmp_path, monkeypatch):
    """A nonexistent (and uncreatable) skill_dir yields 422 SKILL_DIR_NOT_WRITABLE."""
    app = _app(tmp_path, monkeypatch, 59632)
    bogus = tmp_path / "no-such" / "nested" / "deep"
    with _client(app) as c:
        r = c.post(
            "/api/v1/agents",
            json={"type": "codex", "name": "bad", "skill_dir": str(bogus)},
        )
        assert r.status_code == 422, r.text
        assert r.json()["error"]["code"] == "SKILL_DIR_NOT_WRITABLE"


@pytest.mark.acceptance(spec="004-agent-registry", scenario="reject unsupported agent type")
def test_error_422_unprocessable_body(tmp_path, monkeypatch):
    """Types outside {claude_code, codex} — including the v1-dropped cursor /
    claude_desktop and any garbage value — are rejected with 422."""
    app = _app(tmp_path, monkeypatch, 59633)
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    with _client(app) as c:
        for bad_type in ("cursor", "claude_desktop", "not_a_real_type"):
            r = c.post(
                "/api/v1/agents",
                json={"type": bad_type, "name": "x", "skill_dir": str(skill_dir)},
            )
            assert r.status_code == 422, f"{bad_type}: {r.text}"
