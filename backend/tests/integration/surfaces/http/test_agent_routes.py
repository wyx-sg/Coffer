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


def _post_codex(c: TestClient, name: str, config_dir: pathlib.Path):
    """Helper to register one codex agent — keeps line widths reasonable."""
    return c.post(
        "/api/v1/agents",
        json={"type": "codex", "name": name, "config_dir": str(config_dir)},
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
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    with _client(app) as c:
        r = c.post(
            "/api/v1/agents",
            json={
                "type": "codex",
                "name": "cur",
                "config_dir": str(config_dir),
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
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    with _client(app) as c:
        r = c.post(
            "/api/v1/agents",
            json={"type": "claude_code", "config_dir": str(config_dir)},
        )
        assert r.status_code == 201, r.text
        assert r.json()["name"] == "claude-code"


def test_agent_get_one(tmp_path, monkeypatch):
    """GET /agents/{name} returns the persisted config_dir."""
    app = _app(tmp_path, monkeypatch, 59602)
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    with _client(app) as c:
        r = c.post(
            "/api/v1/agents",
            json={"type": "codex", "name": "cur", "config_dir": str(config_dir)},
        )
        assert r.status_code == 201, r.text
        r = c.get("/api/v1/agents/cur")
        assert r.status_code == 200
        assert r.json()["config_dir"] == str(config_dir)
        assert "skill_dir" not in r.json()
        assert "skill_dir_override" not in r.json()


def test_agent_list_after_register(tmp_path, monkeypatch):
    """A freshly registered agent appears in the list."""
    app = _app(tmp_path, monkeypatch, 59603)
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    with _client(app) as c:
        _post_codex(c, "cur", config_dir)
        r = c.get("/api/v1/agents")
        assert r.status_code == 200
        assert any(a["name"] == "cur" for a in r.json()["items"])


def test_agent_patch_config_dir(tmp_path, monkeypatch):
    """PATCH updates config_dir (agents have no enable/disable concept)."""
    app = _app(tmp_path, monkeypatch, 59604)
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    new_dir = tmp_path / "cfg2"
    new_dir.mkdir()
    with _client(app) as c:
        _post_codex(c, "cur", config_dir)
        r = c.patch(
            "/api/v1/agents/cur",
            json={"config_dir": str(new_dir)},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["config_dir"] == str(new_dir)
        assert "enabled" not in body


def test_agent_patch_model_binding(tmp_path, monkeypatch):
    """PATCH sets the per-agent model binding; a bad wire_api is rejected."""
    app = _app(tmp_path, monkeypatch, 59609)
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    with _client(app) as c:
        _post_codex(c, "cur", config_dir)
        ok = c.patch("/api/v1/agents/cur", json={"model": "gpt-5", "wire_api": "responses"})
        assert ok.status_code == 200, ok.text
        assert ok.json()["model"] == "gpt-5"
        assert ok.json()["wire_api"] == "responses"
        bad = c.patch("/api/v1/agents/cur", json={"wire_api": "garbage"})
        assert bad.status_code != 200  # validated, not silently persisted


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
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    with _client(app) as c:
        _post_codex(c, "cur", config_dir)
        r = c.delete("/api/v1/agents/cur")
        assert r.status_code == 204
        r = c.get("/api/v1/agents/cur")
        assert r.status_code == 404


def test_patch_description_only_preserves_config_dir(tmp_path, monkeypatch):
    """Regression: a PATCH that omits config_dir must not wipe the override.

    `AgentPatch.config_dir` defaults to None, so "field absent" and "field
    set to null" look identical on the model — the route must use
    `model_fields_set` to tell them apart.
    """
    app = _app(tmp_path, monkeypatch, 59610)
    config_dir = tmp_path / "custom-cfg"
    config_dir.mkdir()

    with _client(app) as c:
        r = c.post(
            "/api/v1/agents",
            json={
                "type": "codex",
                "name": "cur",
                "config_dir": str(config_dir),
                "description": "before",
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["config_dir"] == str(config_dir)

        # PATCH only the description — config_dir is absent from the body.
        r = c.patch("/api/v1/agents/cur", json={"description": "after"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["description"] == "after"
        # The custom config_dir must survive a description-only PATCH.
        assert body["config_dir"] == str(config_dir)

        # And it must still be persisted on a fresh read.
        r = c.get("/api/v1/agents/cur")
        assert r.json()["config_dir"] == str(config_dir)


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


def test_candidates_excludes_disabled_agent_types(tmp_path, monkeypatch):
    """Only the exposed agent types (Claude Code, Codex) are offered as candidates.

    The other manifest entries (Cursor, OpenCode, OpenClaw, Hermes) are wired
    end-to-end on the backend but hidden from discovery (``enabled=False``) until
    each is validated and exposed — even an on-disk marker must not surface them.
    """
    app = _app(tmp_path, monkeypatch, 59621)
    for subpath in (".claude", ".codex"):
        (tmp_path / subpath).mkdir(parents=True)

    with _client(app) as c:
        r = c.get("/api/v1/agents/candidates")
        assert r.status_code == 200, r.text
        types = {cand["type"] for cand in r.json()["candidates"]}
        assert types == {"claude_code", "codex"}, types
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
    # Distinct config dirs so the only collision is the name (not the
    # one-agent-per-config-dir rule, which has its own error code).
    first = tmp_path / "cfg1"
    second = tmp_path / "cfg2"
    first.mkdir()
    second.mkdir()
    with _client(app) as c:
        r = c.post(
            "/api/v1/agents",
            json={"type": "codex", "name": "dup", "config_dir": str(first)},
        )
        assert r.status_code == 201, r.text
        r = c.post(
            "/api/v1/agents",
            json={"type": "claude_code", "name": "dup", "config_dir": str(second)},
        )
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "RESOURCE_ALREADY_EXISTS"


def test_error_422_skill_dir_not_writable(tmp_path, monkeypatch):
    """A config_dir that points at an existing FILE means <config_dir>/skills
    cannot be created — yielding 422 SKILL_DIR_NOT_WRITABLE."""
    app = _app(tmp_path, monkeypatch, 59632)
    bogus_file = tmp_path / "a-file"
    bogus_file.write_text("not a dir")
    with _client(app) as c:
        r = c.post(
            "/api/v1/agents",
            json={"type": "codex", "name": "bad", "config_dir": str(bogus_file)},
        )
        assert r.status_code == 422, r.text
        assert r.json()["error"]["code"] == "SKILL_DIR_NOT_WRITABLE"


@pytest.mark.acceptance(spec="004-agent-registry", scenario="reject unsupported agent type")
def test_error_422_unprocessable_body(tmp_path, monkeypatch):
    """Types outside the supported set — e.g. the unsupported Claude Desktop chat
    app and any garbage value — are rejected with 422."""
    app = _app(tmp_path, monkeypatch, 59633)
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    with _client(app) as c:
        for bad_type in ("claude_desktop", "gemini_cli", "not_a_real_type"):
            r = c.post(
                "/api/v1/agents",
                json={"type": bad_type, "name": "x", "config_dir": str(config_dir)},
            )
            assert r.status_code == 422, f"{bad_type}: {r.text}"
