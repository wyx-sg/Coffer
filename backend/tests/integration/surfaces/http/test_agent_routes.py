"""End-to-end HTTP coverage for /api/v1/agents/* (spec agent-registry).

Every per-agent route is addressed by the agent's ``uid`` — the immutable
identity minted server-side at registration — and never by its name
(ADR resource-identity-is-an-immutable-uid). Only the collection routes
(``GET``/``POST /api/v1/agents``, ``GET /api/v1/agents/candidates``) take no
identity at all.

These tests take the uid straight off the ``POST /api/v1/agents`` response they
already make, which is also the flow a real client follows: create, keep the
uid, address everything by it. The name still travels in the payload, as the
label a person reads, so a test that cares about the label asserts on the body
rather than on the URL.
"""

from __future__ import annotations

import pathlib
import uuid

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


def _codex_uid(c: TestClient, name: str, config_dir: pathlib.Path) -> str:
    """Register one codex agent and return the uid every route addresses it by.

    The uid is read off the creation response rather than looked up afterwards:
    the server mints it, the client keeps it, and no second request is needed
    to learn it.
    """
    r = _post_codex(c, name, config_dir)
    assert r.status_code == 201, r.text
    return r.json()["uid"]


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
        # The identity comes back with the creation, minted server-side —
        # `AgentCreate` has no uid field, so a client cannot choose one. It is
        # distinct from the label by construction: everything addresses the
        # agent by this string, and nothing addresses it by "cur".
        assert body["uid"]
        assert body["uid"] != body["name"]
        assert "auto_detected" not in body


@pytest.mark.acceptance(
    spec="agent-registry", scenario="register an agent without an explicit name"
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
    """GET /agents/{uid} returns the persisted config_dir."""
    app = _app(tmp_path, monkeypatch, 59602)
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    with _client(app) as c:
        r = c.post(
            "/api/v1/agents",
            json={"type": "codex", "name": "cur", "config_dir": str(config_dir)},
        )
        assert r.status_code == 201, r.text
        uid = r.json()["uid"]
        r = c.get(f"/api/v1/agents/{uid}")
        assert r.status_code == 200
        # Both halves of AgentOut's identity contract: the uid the caller
        # addressed, echoed back unchanged, and the label beside it.
        assert r.json()["uid"] == uid
        assert r.json()["name"] == "cur"
        assert r.json()["config_dir"] == str(config_dir)
        assert "skill_dir" not in r.json()
        assert "skill_dir_override" not in r.json()


def test_agent_out_has_no_capability_matrix(tmp_path, monkeypatch):
    """spec agent-registry FR-003: with the supported types narrowed to claude_code + codex, every
    agent supports every facet — so AgentOut carries no capability matrix."""
    app = _app(tmp_path, monkeypatch, 59608)
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    with _client(app) as c:
        uid = _codex_uid(c, "cur", config_dir)
        r = c.get(f"/api/v1/agents/{uid}")
        assert r.status_code == 200, r.text
        assert "capabilities" not in r.json()

        r = c.get("/api/v1/agents")
        assert r.status_code == 200, r.text
        assert all("capabilities" not in item for item in r.json()["items"])


def test_agent_list_after_register(tmp_path, monkeypatch):
    """A freshly registered agent appears in the list, uid and all.

    The list is where a UI gets the uids it will address rows by, so the
    listed entry has to carry the same uid the creation handed back — not a
    name the UI would then have to resolve.
    """
    app = _app(tmp_path, monkeypatch, 59603)
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    with _client(app) as c:
        uid = _codex_uid(c, "cur", config_dir)
        r = c.get("/api/v1/agents")
        assert r.status_code == 200
        listed = [a for a in r.json()["items"] if a["uid"] == uid]
        assert len(listed) == 1, r.text
        assert listed[0]["name"] == "cur"


def test_agent_patch_config_dir(tmp_path, monkeypatch):
    """PATCH updates config_dir (agents have no enable/disable concept)."""
    app = _app(tmp_path, monkeypatch, 59604)
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    new_dir = tmp_path / "cfg2"
    new_dir.mkdir()
    with _client(app) as c:
        uid = _codex_uid(c, "cur", config_dir)
        r = c.patch(
            f"/api/v1/agents/{uid}",
            json={"config_dir": str(new_dir)},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["config_dir"] == str(new_dir)
        # An edit changes what the resource IS, never which resource it is.
        assert body["uid"] == uid
        assert "enabled" not in body


def test_agent_patch_model_binding(tmp_path, monkeypatch):
    """PATCH sets the per-agent model binding; a bad wire_api is rejected."""
    app = _app(tmp_path, monkeypatch, 59609)
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    with _client(app) as c:
        uid = _codex_uid(c, "cur", config_dir)
        ok = c.patch(f"/api/v1/agents/{uid}", json={"model": "gpt-5", "wire_api": "responses"})
        assert ok.status_code == 200, ok.text
        assert ok.json()["model"] == "gpt-5"
        assert ok.json()["wire_api"] == "responses"
        bad = c.patch(f"/api/v1/agents/{uid}", json={"wire_api": "garbage"})
        assert bad.status_code != 200  # validated, not silently persisted
        # "chat" is refused like any other unknown value. It used to be the
        # other half of this setting; Codex 0.139.0 will not load a config.toml
        # carrying it, so accepting it here would hand the user a CLI that does
        # not start and no way to see why.
        dead = c.patch(f"/api/v1/agents/{uid}", json={"wire_api": "chat"})
        assert dead.status_code != 200, dead.text
        assert c.get(f"/api/v1/agents/{uid}").json()["wire_api"] == "responses"


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
        uid = _codex_uid(c, "cur", config_dir)
        r = c.delete(f"/api/v1/agents/{uid}")
        assert r.status_code == 204
        # The uid is retired with the row: it addressed a resource a moment ago
        # and now addresses nothing, which is the only correct answer — a uid is
        # never reissued, so this 404 can never turn back into a 200.
        r = c.get(f"/api/v1/agents/{uid}")
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
        uid = r.json()["uid"]
        assert r.json()["config_dir"] == str(config_dir)

        # PATCH only the description — config_dir is absent from the body.
        r = c.patch(f"/api/v1/agents/{uid}", json={"description": "after"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["description"] == "after"
        # The custom config_dir must survive a description-only PATCH.
        assert body["config_dir"] == str(config_dir)
        # And so must the identity: an edit is an edit, not a re-creation.
        assert body["uid"] == uid

        # And it must still be persisted on a fresh read.
        r = c.get(f"/api/v1/agents/{uid}")
        assert r.json()["config_dir"] == str(config_dir)


def test_uid_survives_a_rename_and_no_name_addresses_the_agent(tmp_path, monkeypatch):
    """The identity stays put when the label moves — the point of the change.

    Renaming is now an ordinary field on the kind-agnostic
    ``PATCH /api/v1/resources/{uid}``; there is no per-kind rename route left
    to call, and an agent never had one. So the rename goes through the
    framework route while the agent surface is read back at the *same* address
    as before. Before the uid existed, a rename was a delete plus a create, and
    everything keyed on the resource — paired chats, capability preferences,
    the audit trail — went with it
    (ADR resource-identity-is-an-immutable-uid).
    """
    app = _app(tmp_path, monkeypatch, 59611)
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    with _client(app) as c:
        uid = _codex_uid(c, "before", config_dir)

        r = c.patch(f"/api/v1/resources/{uid}", json={"name": "after"})
        assert r.status_code == 200, r.text
        assert r.json()["uid"] == uid
        assert r.json()["name"] == "after"

        # Same address, new label, everything else untouched.
        r = c.get(f"/api/v1/agents/{uid}")
        assert r.status_code == 200, r.text
        assert r.json()["uid"] == uid
        assert r.json()["name"] == "after"
        assert r.json()["config_dir"] == str(config_dir)

        # Neither name is an address — not the one it just lost, nor the one it
        # just gained. A name-shaped path segment is simply a uid nothing
        # answers to.
        assert c.get("/api/v1/agents/before").status_code == 404
        assert c.get("/api/v1/agents/after").status_code == 404

        # The one route that goes from a label to a resource answers with the
        # very uid the caller has been holding all along.
        found = c.get("/api/v1/resources", params={"kind": "agent", "name": "after"})
        assert found.status_code == 200, found.text
        assert [res["uid"] for res in found.json()["resources"]] == [uid]


@pytest.mark.acceptance(spec="agent-registry", scenario="discover installed agents as candidates")
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


def test_candidates_offers_exactly_the_manifest_types(tmp_path, monkeypatch):
    """Only the exposed agent types (Claude Code, Codex) are offered as candidates.

    Discovery enumerates the ``enabled=True`` manifest records and nothing else —
    an on-disk marker for a product Coffer does not manage must not surface.
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
    """GET a uid no agent answers to yields a 404 error envelope.

    Both spellings of "not here" are covered, because the route makes no
    distinction between them: a well-formed uid that was never minted, and a
    name-shaped segment that is not a uid at all. The path parameter is a plain
    string looked up as an identity, so an unparseable one is not a 422 — it is
    simply an identity nothing holds.
    """
    app = _app(tmp_path, monkeypatch, 59630)
    with _client(app) as c:
        for absent in (uuid.uuid4().hex, "ghost"):
            r = c.get(f"/api/v1/agents/{absent}")
            assert r.status_code == 404, f"{absent}: {r.text}"
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


@pytest.mark.acceptance(spec="agent-registry", scenario="reject unsupported agent type")
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
