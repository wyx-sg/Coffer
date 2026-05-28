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


def _post_cursor(c: TestClient, name: str, skill_dir: pathlib.Path):
    """Helper to register one cursor agent — keeps line widths reasonable."""
    return c.post(
        "/api/v1/agents",
        json={"type": "cursor", "name": name, "skill_dir": str(skill_dir)},
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
    """POST /agents creates an agent with auto_detected=False."""
    app = _app(tmp_path, monkeypatch, 59601)
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    with _client(app) as c:
        r = c.post(
            "/api/v1/agents",
            json={
                "type": "cursor",
                "name": "cur",
                "skill_dir": str(skill_dir),
                "description": "manual",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["name"] == "cur"
        assert body["type"] == "cursor"
        assert body["auto_detected"] is False
        assert body["enabled"] is True


def test_agent_get_one(tmp_path, monkeypatch):
    """GET /agents/{name} returns the persisted skill_dir."""
    app = _app(tmp_path, monkeypatch, 59602)
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    with _client(app) as c:
        r = c.post(
            "/api/v1/agents",
            json={"type": "cursor", "name": "cur", "skill_dir": str(skill_dir)},
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
        _post_cursor(c, "cur", skill_dir)
        r = c.get("/api/v1/agents")
        assert r.status_code == 200
        assert any(a["name"] == "cur" for a in r.json()["items"])


def test_agent_patch_skill_dir_and_enabled(tmp_path, monkeypatch):
    """PATCH updates skill_dir + toggles enabled."""
    app = _app(tmp_path, monkeypatch, 59604)
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    new_dir = tmp_path / "skills2"
    new_dir.mkdir()
    with _client(app) as c:
        _post_cursor(c, "cur", skill_dir)
        r = c.patch(
            "/api/v1/agents/cur",
            json={"skill_dir": str(new_dir), "enabled": False},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["skill_dir"] == str(new_dir)
        assert body["enabled"] is False


def test_agent_detect_post(tmp_path, monkeypatch):
    """POST /agents/detect is callable + returns 200 even with no markers."""
    app = _app(tmp_path, monkeypatch, 59605)
    with _client(app) as c:
        r = c.post("/api/v1/agents/detect")
        assert r.status_code == 200, r.text
        assert "registered" in r.json()


def test_agent_delete_then_404(tmp_path, monkeypatch):
    """DELETE removes the agent; subsequent GET yields 404."""
    app = _app(tmp_path, monkeypatch, 59606)
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    with _client(app) as c:
        _post_cursor(c, "cur", skill_dir)
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
                "type": "cursor",
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
    spec="004-agent-registry", scenario="detect installed agents on first launch"
)
def test_detect_endpoint_registers_marker_present_agents(tmp_path, monkeypatch):
    """After the first /detect call with marker dirs present, those agents appear."""
    app = _app(tmp_path, monkeypatch, 59620)
    # Create both the marker dir AND the actual default skill_dir so the
    # service-layer writability check (FR-007) passes when auto-detect calls
    # register(skill_dir=None) and resolves the default path.
    (tmp_path / ".cursor" / "skills").mkdir(parents=True)
    (tmp_path / ".claude" / "skills").mkdir(parents=True)

    with _client(app) as c:
        # The lifespan already kicked off run_once asynchronously. Wait a beat
        # or force a re-scan via the endpoint to ensure deterministic state.
        # Calling /detect is idempotent — it won't register agents twice.
        r = c.post("/api/v1/agents/detect")
        assert r.status_code == 200

        r = c.get("/api/v1/agents")
        items = r.json()["items"]
        types = {a["type"] for a in items}
        assert "cursor" in types
        assert "claude_code" in types
        # auto_detected flag set
        for a in items:
            if a["type"] in {"cursor", "claude_code"}:
                assert a["auto_detected"] is True


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
            json={"type": "cursor", "name": "dup", "skill_dir": str(skill_dir)},
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
            json={"type": "cursor", "name": "bad", "skill_dir": str(bogus)},
        )
        assert r.status_code == 422, r.text
        assert r.json()["error"]["code"] == "SKILL_DIR_NOT_WRITABLE"


def test_error_422_unprocessable_body(tmp_path, monkeypatch):
    """An invalid AgentType value yields 422 (FastAPI validation)."""
    app = _app(tmp_path, monkeypatch, 59633)
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    with _client(app) as c:
        r = c.post(
            "/api/v1/agents",
            json={"type": "not_a_real_type", "name": "x", "skill_dir": str(skill_dir)},
        )
        assert r.status_code == 422
