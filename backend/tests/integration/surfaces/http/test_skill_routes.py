"""End-to-end HTTP coverage for /api/v1/skills/* (spec agent-registry)."""

from __future__ import annotations

import pathlib
import textwrap

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-003"


def _app(tmp_path: pathlib.Path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    return create_app()


def _client(app) -> TestClient:
    set_active_token(TOKEN)
    return TestClient(app, headers={"X-Coffer-Token": TOKEN})


def _write_skill_folder(folder: pathlib.Path, *, name: str) -> pathlib.Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        textwrap.dedent(
            f"""\
            ---
            name: {name}
            description: A test skill named {name}.
            ---

            body
            """
        ),
        encoding="utf-8",
    )
    return folder


@pytest.mark.acceptance(spec="skill-manager", scenario="desktop and CLI cover every operation")
def test_skill_full_lifecycle_via_http(tmp_path, monkeypatch):
    """End-to-end HTTP coverage — the surface both desktop and CLI consume."""
    app = _app(tmp_path, monkeypatch, 59600)

    # Register an agent so import auto-binds against it.
    # Registration auto-creates <config_dir>/skills, where skills are delivered.
    agent_config_dir = tmp_path / "agent-cfg"
    agent_config_dir.mkdir()
    src = tmp_path / "src"
    _write_skill_folder(src, name="hello-world")

    with _client(app) as c:
        # register an agent
        r = c.post(
            "/api/v1/agents",
            json={"type": "claude_code", "name": "cur", "config_dir": str(agent_config_dir)},
        )
        assert r.status_code == 201, r.text

        # list skills — just Coffer's own, which it seeds for itself at boot
        # (spec knowledge FR-034). The user has imported nothing yet, so the
        # lifecycle below is measured against that one row.
        r = c.get("/api/v1/skills")
        assert r.status_code == 200
        assert [i["name"] for i in r.json()["items"]] == ["coffer-guide"]

        # import
        r = c.post("/api/v1/skills/import", json={"path": str(src)})
        assert r.status_code == 201, r.text
        skill = r.json()
        assert skill["name"] == "hello-world"
        assert [b["agent_name"] for b in skill["bindings"]] == ["cur"]
        # Delivery is decided by these two fields and nothing else.
        assert skill["enabled"] is True
        assert skill["scope"] is None

        # link exists on disk at <config_dir>/skills/<skill>
        link = agent_config_dir / "skills" / "hello-world"
        assert link.exists()

        # get
        r = c.get("/api/v1/skills/hello-world")
        assert r.status_code == 200

        # verify — no drift
        r = c.post("/api/v1/skills/verify")
        assert r.status_code == 200
        assert r.json()["entries"] == []

        # the per-(skill, agent) enable/disable routes are gone — delivery is
        # driven by the skill's own scope + enabled flag. Assert only that
        # nothing is reachable there: an unrouted path answers 404 or 405
        # depending on the Starlette version, and which one is not the point.
        for gone in ("enable", "disable"):
            r = c.post(f"/api/v1/skills/hello-world/{gone}", json={"agent_name": "cur"})
            assert r.status_code in (404, 405), f"{gone} still routes: {r.status_code}"

        # scope the skill away from the agent — the copy is reclaimed
        r = c.put(
            "/api/v1/resources/skill/hello-world/scope",
            json={"scope": {"agents": []}},
        )
        assert r.status_code == 200, r.text
        assert r.json()["scope"] == {"agents": []}
        assert not link.exists()
        assert c.get("/api/v1/skills/hello-world").json()["bindings"] == []

        # scope it back in — redelivered
        r = c.put(
            "/api/v1/resources/skill/hello-world/scope",
            json={"scope": {"agents": ["cur"]}},
        )
        assert r.status_code == 200, r.text
        assert r.json()["scope"] == {"agents": ["cur"]}
        assert link.exists()

        # a stale client still sending the withdrawn machine axis is REFUSED,
        # not quietly obeyed minus the key it does not understand. Obeying it
        # would store `agents: null` — every agent — from a request whose whole
        # point was to narrow, which is the one direction a write must never
        # take by accident.
        r = c.put(
            "/api/v1/resources/skill/hello-world/scope",
            json={"scope": {"agents": None, "machines": ["a3f21c9e4b7d2610"]}},
        )
        assert r.status_code == 422, r.text
        assert c.get("/api/v1/resources/skill/hello-world/scope").json()["scope"] == {
            "agents": ["cur"]
        }
        assert link.exists()

        # disabling the skill resource reclaims it; re-enabling redelivers
        assert c.post("/api/v1/resources/skill/hello-world/disable").status_code == 200
        assert not link.exists()
        assert c.post("/api/v1/resources/skill/hello-world/enable").status_code == 200
        assert link.exists()

        # delete
        r = c.delete("/api/v1/skills/hello-world")
        assert r.status_code == 204
        assert not link.exists()
        r = c.get("/api/v1/skills/hello-world")
        assert r.status_code == 404


def test_deleting_agent_cascades_into_skill_binding_cleanup(tmp_path, monkeypatch):
    """CODE-WIRING: exercise the real composition-root cross-kind hook.

    ``agent_skill_wiring._agent_on_delete`` (wired only in the assembled app,
    previously untested — the unit skill tests build their own wiring) must,
    when an agent is deleted, tear down every per-agent skill symlink and drop
    the binding row. We drive it end-to-end through create_app().
    """
    app = _app(tmp_path, monkeypatch, 59620)
    agent_config_dir = tmp_path / "agent-cfg"
    agent_config_dir.mkdir()
    src = tmp_path / "src"
    _write_skill_folder(src, name="hello-world")

    with _client(app) as c:
        r = c.post(
            "/api/v1/agents",
            json={"type": "claude_code", "name": "cur", "config_dir": str(agent_config_dir)},
        )
        assert r.status_code == 201, r.text

        r = c.post("/api/v1/skills/import", json={"path": str(src)})
        assert r.status_code == 201, r.text
        link = agent_config_dir / "skills" / "hello-world"
        assert link.exists(), "skill should be delivered to the agent on import"

        # Delete the agent — the cross-kind on_delete hook must cascade.
        r = c.delete("/api/v1/agents/cur")
        assert r.status_code == 204, r.text

        # The per-agent symlink is torn down...
        assert not link.exists(), "agent delete must remove its delivered skill link"
        # ...and the skill no longer lists a binding for the deleted agent.
        r = c.get("/api/v1/skills/hello-world")
        assert r.status_code == 200
        assert all(b["agent_name"] != "cur" for b in r.json()["bindings"])


# TEST21-010: error envelope shape for non-SSRF errors. The envelope is
# `{error: {code, message, details}}` — without this assertion only the
# SSRF code is pinned, leaving other surfaces free to regress to a bare
# string body or an alternative shape.
def test_404_envelope_shape_for_missing_skill(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59610)
    with _client(app) as c:
        r = c.get("/api/v1/skills/does-not-exist")
        assert r.status_code == 404
        body = r.json()
        assert "error" in body
        err = body["error"]
        assert isinstance(err.get("code"), str) and err["code"]
        assert isinstance(err.get("message"), str)
        # `details` is always present (may be {}); never absent.
        assert "details" in err


def test_conflict_envelope_shape_on_duplicate_import(tmp_path, monkeypatch):
    """Re-importing the same skill name yields a 409 with the standard envelope."""
    app = _app(tmp_path, monkeypatch, 59612)
    src = tmp_path / "src"
    _write_skill_folder(src, name="dup")
    with _client(app) as c:
        r = c.post("/api/v1/skills/import", json={"path": str(src)})
        assert r.status_code == 201
        # Same source → same name → AlreadyExists (no overwrite flag).
        r = c.post("/api/v1/skills/import", json={"path": str(src)})
        assert r.status_code == 409
        body = r.json()
        assert "error" in body
        assert body["error"].get("code")
        assert isinstance(body["error"].get("message"), str)


def test_reimport_with_overwrite_replaces(tmp_path, monkeypatch):
    """Re-importing with overwrite=true replaces the skill instead of 409."""
    app = _app(tmp_path, monkeypatch, 59614)
    src = tmp_path / "src"
    _write_skill_folder(src, name="dup")
    with _client(app) as c:
        # First import — fresh
        r = c.post("/api/v1/skills/import", json={"path": str(src)})
        assert r.status_code == 201, r.text
        first_hash = r.json()["version_hash"]

        # Modify the skill content so version_hash changes.
        (src / "SKILL.md").write_text(
            textwrap.dedent(
                """\
                ---
                name: dup
                description: Updated description.
                ---

                updated body
                """
            ),
            encoding="utf-8",
        )

        # Re-import with overwrite=true — must succeed (201, not 409).
        r = c.post("/api/v1/skills/import", json={"path": str(src), "overwrite": True})
        assert r.status_code == 201, r.text
        skill = r.json()
        assert skill["name"] == "dup"
        assert skill["version_hash"] != first_hash


def test_import_cannot_overwrite_a_skill_coffer_generates(tmp_path, monkeypatch):
    """The name of a builtin skill is reserved against an overwriting import.

    DELETE already refuses a builtin skill, but the guard reads the row's
    ``source``. An import with ``overwrite=true`` from a folder whose
    frontmatter says ``coffer-guide`` rewrote that field to ``local_import``,
    and the protection went with it: the skill was deletable until the next
    boot seeded it back. The rule is about *generated* skills, not about one
    magic name — the same ``is_builtin`` predicate decides all three.
    """
    app = _app(tmp_path, monkeypatch, 59618)
    src = tmp_path / "impostor"
    _write_skill_folder(src, name="coffer-guide")
    with _client(app) as c:
        # The seeded builtin is there to begin with.
        before = c.get("/api/v1/skills/coffer-guide")
        assert before.status_code == 200, before.text
        assert before.json()["builtin"] is True

        r = c.post("/api/v1/skills/import", json={"path": str(src), "overwrite": True})
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "RESOURCE_PROTECTED"

        # Untouched: still builtin, so DELETE is still refused.
        after = c.get("/api/v1/skills/coffer-guide")
        assert after.json()["source"] == {"type": "builtin"}
        assert after.json()["builtin"] is True
        assert after.json()["version_hash"] == before.json()["version_hash"]
        assert c.delete("/api/v1/skills/coffer-guide").status_code == 409


def test_import_without_overwrite_still_reports_the_reservation(tmp_path, monkeypatch):
    """Even the plain 409 path names the right reason for a builtin name."""
    app = _app(tmp_path, monkeypatch, 59620)
    src = tmp_path / "impostor"
    _write_skill_folder(src, name="coffer-guide")
    with _client(app) as c:
        r = c.post("/api/v1/skills/import", json={"path": str(src)})
        assert r.status_code == 409, r.text
        # Without --force this is an ordinary name clash; the reservation is
        # what ``overwrite=true`` would otherwise have walked around.
        assert r.json()["error"]["code"] == "RESOURCE_ALREADY_EXISTS"


def test_skill_repair_route(tmp_path, monkeypatch):
    """POST /skills/repair re-delivers MISSING_LINK and leaves REPLACED_WITH_REGULAR intact."""
    app = _app(tmp_path, monkeypatch, 59630)
    agent_config_dir = tmp_path / "agent-cfg"
    agent_config_dir.mkdir()
    src = tmp_path / "src"
    _write_skill_folder(src, name="fix-me")

    with _client(app) as c:
        # Register agent and import skill (creates binding + link).
        r = c.post(
            "/api/v1/agents",
            json={"type": "claude_code", "name": "cur", "config_dir": str(agent_config_dir)},
        )
        assert r.status_code == 201, r.text

        r = c.post("/api/v1/skills/import", json={"path": str(src)})
        assert r.status_code == 201, r.text

        link = agent_config_dir / "skills" / "fix-me"
        assert link.exists()

        # Introduce MISSING_LINK drift by removing the symlink.
        link.unlink()
        assert not link.exists()

        # Introduce a REPLACED_WITH_REGULAR drift for another skill.
        src2 = tmp_path / "src2"
        _write_skill_folder(src2, name="foreign")
        r2 = c.post("/api/v1/skills/import", json={"path": str(src2)})
        assert r2.status_code == 201, r2.text
        foreign_link = agent_config_dir / "skills" / "foreign"
        # Replace the symlink with a regular directory (simulates REPLACED_WITH_REGULAR).
        foreign_link.unlink()
        foreign_link.mkdir()
        (foreign_link / "file.txt").write_text("foreign content")

        # Call repair.
        r = c.post("/api/v1/skills/repair")
        assert r.status_code == 200, r.text
        body = r.json()

        # The MISSING_LINK should be remediated.
        assert any(e["skill_name"] == "fix-me" for e in body["remediated"]), body
        # The link is restored.
        assert link.exists()

        # The REPLACED_WITH_REGULAR should remain (manual action needed).
        assert any(e["skill_name"] == "foreign" for e in body["remaining"]["entries"]), body
        # Foreign dir is untouched.
        assert (foreign_link / "file.txt").exists()
