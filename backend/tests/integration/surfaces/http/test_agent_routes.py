"""End-to-end HTTP coverage for /api/v1/agents/* (spec agent-registry).

Every per-agent route is addressed by the agent's ``uid`` — the immutable
identity minted server-side at registration — and never by its name
(ADR identity-is-the-uid-inside-the-file). Only the collection routes
(``GET``/``POST /api/v1/agents``, ``GET /api/v1/agents/candidates``) take no
identity at all.

These tests take the uid straight off the ``POST /api/v1/agents`` response they
already make, which is also the flow a real client follows: create, keep the
uid, address everything by it. An agent's name is its type's (spec
agent-registry "Keep one agent per type, named by it"), so a registration
carries only the type and, optionally, a config directory; the type standing in
for the uid in a path is covered in ``test_agent_one_per_type.py``.
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


def _post_codex(c: TestClient, config_dir: pathlib.Path):
    """Register the one codex agent at ``config_dir``."""
    return c.post("/api/v1/agents", json={"type": "codex", "config_dir": str(config_dir)})


def _codex_uid(c: TestClient, config_dir: pathlib.Path) -> str:
    """Register one codex agent and return the uid every route addresses it by.

    The uid is read off the creation response rather than looked up afterwards:
    the server mints it, the client keeps it, and no second request is needed
    to learn it.
    """
    r = _post_codex(c, config_dir)
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
        r = _post_codex(c, config_dir)
        assert r.status_code == 201, r.text
        body = r.json()
        assert (body["name"], body["display_name"], body["type"]) == (
            "codex",
            "OpenAI Codex",
            "codex",
        )
        # The identity comes back with the creation, minted server-side —
        # `AgentCreate` has no uid field, so a client cannot choose one.
        assert body["uid"]
        assert body["uid"] != body["name"]
        # An agent carries neither a title nor a description.
        assert "title" not in body
        assert "description" not in body
        assert "auto_detected" not in body


@pytest.mark.acceptance(
    spec="agent-registry", scenario="register an agent without an explicit name"
)
def test_agent_register_without_name_defaults_to_type(tmp_path, monkeypatch):
    """POST /agents takes only the type: the name is the type's
    (claude_code -> claude-code), audited as ``resource_created``."""
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
        uid = r.json()["uid"]
        audit = c.get("/api/v1/audit", params={"resource_uid": uid}).json()["entries"]
        assert "resource_created" in [e["event_type"] for e in audit]


def test_agent_get_one(tmp_path, monkeypatch):
    """GET /agents/{uid} returns the persisted config_dir."""
    app = _app(tmp_path, monkeypatch, 59602)
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    with _client(app) as c:
        uid = _codex_uid(c, config_dir)
        r = c.get(f"/api/v1/agents/{uid}")
        assert r.status_code == 200
        # Both halves of AgentOut's identity contract: the uid the caller
        # addressed, echoed back unchanged, and the label beside it.
        assert r.json()["uid"] == uid
        assert r.json()["name"] == "codex"
        assert r.json()["config_dir"] == str(config_dir)
        assert "skill_dir" not in r.json()
        assert "skill_dir_override" not in r.json()


def test_agent_out_has_no_capability_matrix(tmp_path, monkeypatch):
    """Per "Support exactly the Claude Code and Codex agent types": with the
    supported types narrowed to claude_code + codex, every agent supports every
    facet — so AgentOut carries no capability matrix."""
    app = _app(tmp_path, monkeypatch, 59608)
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    with _client(app) as c:
        uid = _codex_uid(c, config_dir)
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
        uid = _codex_uid(c, config_dir)
        r = c.get("/api/v1/agents")
        assert r.status_code == 200
        listed = [a for a in r.json()["items"] if a["uid"] == uid]
        assert len(listed) == 1, r.text
        assert listed[0]["name"] == "codex"


def test_agent_patch_config_dir(tmp_path, monkeypatch):
    """PATCH updates config_dir."""
    app = _app(tmp_path, monkeypatch, 59604)
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    new_dir = tmp_path / "cfg2"
    new_dir.mkdir()
    with _client(app) as c:
        uid = _codex_uid(c, config_dir)
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
    """PATCH sets the per-agent model binding; the agent carries no wire_api."""
    app = _app(tmp_path, monkeypatch, 59609)
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    with _client(app) as c:
        uid = _codex_uid(c, config_dir)
        ok = c.patch(f"/api/v1/agents/{uid}", json={"model": "gpt-5"})
        assert ok.status_code == 200, ok.text
        assert ok.json()["model"] == "gpt-5"
        assert "wire_api" not in ok.json()


def _connection(c: TestClient) -> str:
    r = c.post(
        "/api/v1/providers",
        json={
            "name": "gw",
            "protocol": "openai",
            "base_url": "https://gw/v1",
            "secret_value": "sk-x",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["uid"]


@pytest.mark.acceptance(
    spec="agent-registry", scenario="an agent reports the connection it runs on"
)
def test_agent_reports_the_connection_it_runs_on(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59611)
    (tmp_path / "cx").mkdir()
    (tmp_path / "cc").mkdir()
    with _client(app) as c:
        uid = _codex_uid(c, tmp_path / "cx")
        other = c.post(
            "/api/v1/agents", json={"type": "claude_code", "config_dir": str(tmp_path / "cc")}
        )
        assert other.status_code == 201, other.text
        connection = _connection(c)
        switched = c.post(f"/api/v1/providers/{connection}/activate", json={"agent_type": "codex"})
        assert switched.status_code == 200, switched.text

        assert c.get(f"/api/v1/agents/{uid}").json()["connection_uid"] == connection
        assert c.get(f"/api/v1/agents/{other.json()['uid']}").json()["connection_uid"] is None


@pytest.mark.acceptance(
    spec="agent-registry", scenario="an agent's update does not switch its connection"
)
def test_agent_patch_does_not_switch_the_connection(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59612)
    cfg = tmp_path / "cx"
    cfg.mkdir()
    with _client(app) as c:
        uid = _codex_uid(c, cfg)
        connection = _connection(c)
        r = c.patch(f"/api/v1/agents/{uid}", json={"connection_uid": connection})
        assert r.status_code == 200, r.text
        assert r.json()["connection_uid"] is None
        assert not (cfg / "config.toml").exists()


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
        uid = _codex_uid(c, config_dir)
        r = c.delete(f"/api/v1/agents/{uid}")
        assert r.status_code == 204
        # The uid is retired with the row: it addressed a resource a moment ago
        # and now addresses nothing, which is the only correct answer — a uid is
        # never reissued, so this 404 can never turn back into a 200.
        r = c.get(f"/api/v1/agents/{uid}")
        assert r.status_code == 404


def test_patch_model_only_preserves_config_dir(tmp_path, monkeypatch):
    """Regression: a PATCH that omits config_dir must not wipe the override.

    `AgentPatch.config_dir` defaults to None, so "field absent" and "field
    set to null" look identical on the model — the route must use
    `model_fields_set` to tell them apart.
    """
    app = _app(tmp_path, monkeypatch, 59610)
    config_dir = tmp_path / "custom-cfg"
    config_dir.mkdir()

    with _client(app) as c:
        uid = _codex_uid(c, config_dir)

        # PATCH only the model — config_dir is absent from the body.
        r = c.patch(f"/api/v1/agents/{uid}", json={"model": "gpt-5"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["model"] == "gpt-5"
        # The custom config_dir must survive a model-only PATCH.
        assert body["config_dir"] == str(config_dir)
        # And so must the identity: an edit is an edit, not a re-creation.
        assert body["uid"] == uid

        # And it must still be persisted on a fresh read.
        r = c.get(f"/api/v1/agents/{uid}")
        assert r.json()["config_dir"] == str(config_dir)


@pytest.mark.acceptance(spec="agent-registry", scenario="keep an agent's uid across a rename")
def test_uid_survives_a_refused_rename_and_no_name_addresses_the_agent(tmp_path, monkeypatch):
    """An agent's name is its type's, so a rename through the kind-agnostic
    ``PATCH /api/v1/resources/{uid}`` is refused with NAME_IMMUTABLE — and the
    agent is read back at the same uid, name and directory as before."""
    app = _app(tmp_path, monkeypatch, 59611)
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    with _client(app) as c:
        uid = _codex_uid(c, config_dir)

        r = c.patch(f"/api/v1/resources/{uid}", json={"name": "after"})
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "NAME_IMMUTABLE"

        r = c.get(f"/api/v1/agents/{uid}")
        assert r.status_code == 200, r.text
        assert (r.json()["uid"], r.json()["name"], r.json()["config_dir"]) == (
            uid,
            "codex",
            str(config_dir),
        )

        # The refused name is not an address, and names nothing.
        assert c.get("/api/v1/agents/after").status_code == 404
        found = c.get("/api/v1/resources", params={"kind": "agent", "name": "after"})
        assert found.status_code == 200, found.text
        assert found.json()["resources"] == []


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
        by_type = {c_["type"]: c_ for c_ in cands}
        # At most one candidate per type, named by the type.
        assert len(cands) == len(by_type)
        assert by_type["codex"]["name"] == "codex"
        assert by_type["claude_code"]["name"] == "claude-code"
        # Each candidate carries the fields the UI needs to confirm an add.
        for c_ in cands:
            assert c_["display_name"]
            assert c_["config_dir"]
            assert c_["standard_config_dir"]
            assert c_["default_skill_dir"]
            assert c_["uid"] is None
            assert isinstance(c_["addable"], bool)
            assert "suggested_name" not in c_

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


@pytest.mark.acceptance(spec="agent-registry", scenario="reject duplicate agent name")
def test_error_409_second_agent_of_a_type(tmp_path, monkeypatch):
    """A second agent of a registered type — its name would be the same — is
    refused with 409 AGENT_TYPE_REGISTERED, even on another directory."""
    app = _app(tmp_path, monkeypatch, 59631)
    first = tmp_path / "cfg1"
    second = tmp_path / "cfg2"
    first.mkdir()
    second.mkdir()
    with _client(app) as c:
        uid = _codex_uid(c, first)
        r = _post_codex(c, second)
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "AGENT_TYPE_REGISTERED"
        assert [(a["uid"], a["name"]) for a in c.get("/api/v1/agents").json()["items"]] == [
            (uid, "codex")
        ]


def test_error_422_skill_dir_not_writable(tmp_path, monkeypatch):
    """A config_dir that points at an existing FILE means <config_dir>/skills
    cannot be created — yielding 422 SKILL_DIR_NOT_WRITABLE."""
    app = _app(tmp_path, monkeypatch, 59632)
    bogus_file = tmp_path / "a-file"
    bogus_file.write_text("not a dir")
    with _client(app) as c:
        r = c.post(
            "/api/v1/agents",
            json={"type": "codex", "config_dir": str(bogus_file)},
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
                json={"type": bad_type, "config_dir": str(config_dir)},
            )
            assert r.status_code == 422, f"{bad_type}: {r.text}"


def test_agent_out_carries_no_title(tmp_path, monkeypatch):
    """spec resource-framework "Carry an optional editable title on the kinds
    that have one": an agent is not one of them — its reads carry no title, a
    title through the kind-agnostic update is refused (422), and the generic
    resource read keeps ``title`` null."""
    app = _app(tmp_path, monkeypatch, 59796)
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    with _client(app) as c:
        uid = _codex_uid(c, config_dir)
        assert "title" not in c.get(f"/api/v1/agents/{uid}").json()

        r = c.patch(f"/api/v1/resources/{uid}", json={"title": "Work Codex"})
        assert r.status_code == 422, r.text
        assert c.get(f"/api/v1/resources/{uid}").json()["title"] is None
        items = {a["uid"]: a for a in c.get("/api/v1/agents").json()["items"]}
        assert "title" not in items[uid]
