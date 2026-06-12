"""HTTP-level tests for /api/v1/memory_stores/{name}/projections/* (spec 007).

Drives the real wired stack (memory + agent + projection composition root)
against a temp HOME. Establishes a projection into a Codex agent (RENDER mode,
no symlink so it works fully in-process), lists it, and removes it.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_TOKEN = "projection-routes-token"
_HEADERS = {"X-Coffer-Token": _TOKEN}


def _app(tmp_path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(tmp_path / "memory"))
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    # The Codex config dir must exist for agent registration's skill-dir check.
    (tmp_path / ".codex").mkdir(parents=True, exist_ok=True)
    return create_app()


def _register_codex(c: TestClient, tmp_path) -> None:
    r = c.post(
        "/api/v1/agents",
        json={"type": "codex", "name": "codex-x", "config_dir": str(tmp_path / ".codex")},
        headers=_HEADERS,
    )
    assert r.status_code in (200, 201), r.text


def test_establish_list_and_remove_projection(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59900)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        _register_codex(c, tmp_path)
        # Seed a fact so the rendered block has content.
        c.post(
            "/api/v1/memory_stores/global/facts",
            json={"text": "deploys via make release", "name": "deploy"},
            headers={**_HEADERS, "X-Coffer-Actor": "user"},
        )

        est = c.post(
            "/api/v1/memory_stores/global/projections",
            json={"agent_ref": "codex-x"},
            headers=_HEADERS,
        )
        assert est.status_code == 200, est.text
        body = est.json()
        assert body["agent_ref"] == "codex-x"
        assert body["projection_mode"] == "RENDER"
        assert body["native_memory_disabled"] is True
        # AGENTS.md got the managed block.
        agents = (tmp_path / ".codex" / "AGENTS.md").read_text(encoding="utf-8")
        assert "coffer:memory:start" in agents

        listed = c.get("/api/v1/memory_stores/global/projections", headers=_HEADERS)
        assert listed.status_code == 200
        assert any(p["agent_ref"] == "codex-x" for p in listed.json()["projections"])

        removed = c.request(
            "DELETE",
            "/api/v1/memory_stores/global/projections/codex-x",
            headers=_HEADERS,
        )
        assert removed.status_code == 204
        # Block stripped; binding gone.
        agents_after = (tmp_path / ".codex" / "AGENTS.md").read_text(encoding="utf-8")
        assert "coffer:memory:start" not in agents_after
        listed2 = c.get("/api/v1/memory_stores/global/projections", headers=_HEADERS)
        assert listed2.json()["projections"] == []


def test_remove_unknown_projection_returns_404(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59910)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.request(
            "DELETE",
            "/api/v1/memory_stores/global/projections/nobody",
            headers=_HEADERS,
        )
        assert r.status_code == 404, r.text


def test_establish_projection_unknown_agent_404(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59920)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post(
            "/api/v1/memory_stores/global/projections",
            json={"agent_ref": "ghost"},
            headers=_HEADERS,
        )
        assert r.status_code == 404, r.text


@pytest.mark.acceptance(spec="007-memory", scenario="agent forgets a fact")
def test_memory_change_rerenders_projection(tmp_path, monkeypatch):
    """A memory write after a projection is established re-renders the managed
    block (FR-013 idempotent re-render on change). Also exercises the forget
    path's projection re-render."""
    app = _app(tmp_path, monkeypatch, 59930)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        _register_codex(c, tmp_path)
        fid = c.post(
            "/api/v1/memory_stores/global/facts",
            json={"text": "first fact", "name": "first"},
            headers={**_HEADERS, "X-Coffer-Actor": "user"},
        ).json()["id"]
        c.post(
            "/api/v1/memory_stores/global/projections",
            json={"agent_ref": "codex-x"},
            headers=_HEADERS,
        )
        # Add a second fact → the managed block re-renders to include it.
        c.post(
            "/api/v1/memory_stores/global/facts",
            json={"text": "second fact", "name": "second"},
            headers={**_HEADERS, "X-Coffer-Actor": "user"},
        )
        agents = (tmp_path / ".codex" / "AGENTS.md").read_text(encoding="utf-8")
        assert "second" in agents
        # Forget the first → re-render no longer lists it.
        c.request(
            "DELETE",
            f"/api/v1/memory_stores/global/facts/{fid}",
            headers={**_HEADERS, "X-Coffer-Actor": "user"},
        )
        agents2 = (tmp_path / ".codex" / "AGENTS.md").read_text(encoding="utf-8")
        assert "first" not in agents2
        assert "second" in agents2


def test_codex_project_binding_rerenders_on_memory_change(tmp_path, monkeypatch):
    # A Codex PROJECT binding renders its managed block into <project>/AGENTS.md.
    # A later memory change must refresh that block in place — re-establishing
    # with project_root=None used to raise (swallowed) and the block went stale
    # (finding #4).
    app = _app(tmp_path, monkeypatch, 59940)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        _register_codex(c, tmp_path)
        project = tmp_path / "repo"
        project.mkdir()
        store = "project-03ABCDEF03ABCDEF03ABCDEF03"
        c.post(
            f"/api/v1/memory_stores/{store}/facts",
            json={"text": "alpha fact", "name": "alpha"},
            headers={**_HEADERS, "X-Coffer-Actor": "user"},
        )
        est = c.post(
            f"/api/v1/memory_stores/{store}/projections",
            json={"agent_ref": "codex-x", "project_root": str(project)},
            headers=_HEADERS,
        )
        assert est.status_code == 200, est.text
        assert est.json()["target_path"] == str(project / "AGENTS.md")
        assert "alpha" in (project / "AGENTS.md").read_text(encoding="utf-8")

        # A memory change refreshes the project block at its stored target.
        c.post(
            f"/api/v1/memory_stores/{store}/facts",
            json={"text": "beta fact", "name": "beta"},
            headers={**_HEADERS, "X-Coffer-Actor": "user"},
        )
        agents = (project / "AGENTS.md").read_text(encoding="utf-8")
        assert "beta" in agents  # block refreshed, not stale


def test_deleting_store_removes_bindings_and_projection_targets(tmp_path, monkeypatch):
    # Deleting a memory store must tear down every projection of it: the native
    # managed block is stripped AND the binding rows are gone (finding #6).
    app = _app(tmp_path, monkeypatch, 59950)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        _register_codex(c, tmp_path)
        project = tmp_path / "repo2"
        project.mkdir()
        store = "project-04ABCDEF04ABCDEF04ABCDEF04"
        c.post(
            f"/api/v1/memory_stores/{store}/facts",
            json={"text": "doomed fact", "name": "doomed"},
            headers={**_HEADERS, "X-Coffer-Actor": "user"},
        )
        c.post(
            f"/api/v1/memory_stores/{store}/projections",
            json={"agent_ref": "codex-x", "project_root": str(project)},
            headers=_HEADERS,
        )
        agents_path = project / "AGENTS.md"
        assert "coffer:memory:start" in agents_path.read_text(encoding="utf-8")

        # Delete the store via the generic resource route (fires the kind hook).
        deleted = c.request("DELETE", f"/api/v1/resources/memory/{store}", headers=_HEADERS)
        assert deleted.status_code == 204, deleted.text

        # Managed block stripped from the native file, file otherwise intact.
        assert "coffer:memory:start" not in agents_path.read_text(encoding="utf-8")
        # And the binding row is gone (a fresh store of the same name lists none).
        listed = c.get(f"/api/v1/memory_stores/{store}/projections", headers=_HEADERS)
        assert listed.json()["projections"] == []


def test_project_root_must_be_an_existing_directory(tmp_path, monkeypatch):
    """FR-020: an absent / relative project_root is rejected with 400 before
    any filesystem mutation (review: untested fix path)."""
    app = _app(tmp_path, monkeypatch, 59930)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        _register_codex(c, tmp_path)
        store = "project-04ABCDEF04ABCDEF04ABCDEF04"
        c.post(
            f"/api/v1/memory_stores/{store}/facts",
            json={"text": "seed", "name": "s"},
            headers={**_HEADERS, "X-Coffer-Actor": "user"},
        )
        for bad_root in [str(tmp_path / "does-not-exist"), "relative/path"]:
            r = c.post(
                f"/api/v1/memory_stores/{store}/projections",
                json={"agent_ref": "codex-x", "project_root": bad_root},
                headers=_HEADERS,
            )
            assert r.status_code == 400, (bad_root, r.text)
            assert r.json()["error"]["code"] == "BAD_REQUEST"


def test_establish_and_remove_emit_memory_projected_audit(tmp_path, monkeypatch):
    """FR-020: every establish/remove writes a ``memory_projected`` audit row."""
    app = _app(tmp_path, monkeypatch, 59940)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        _register_codex(c, tmp_path)
        project = tmp_path / "proj"
        project.mkdir()
        store = "project-05ABCDEF05ABCDEF05ABCDEF05"
        c.post(
            f"/api/v1/memory_stores/{store}/facts",
            json={"text": "seed fact", "name": "s"},
            headers={**_HEADERS, "X-Coffer-Actor": "user"},
        )
        est = c.post(
            f"/api/v1/memory_stores/{store}/projections",
            json={"agent_ref": "codex-x", "project_root": str(project)},
            headers=_HEADERS,
        )
        assert est.status_code == 200, est.text
        rm = c.delete(
            f"/api/v1/memory_stores/{store}/projections/codex-x",
            headers=_HEADERS,
        )
        assert rm.status_code == 204, rm.text

        audit = c.get(
            "/api/v1/audit",
            params={"event_type": "memory_projected", "limit": 50},
            headers=_HEADERS,
        )
        assert audit.status_code == 200, audit.text
        entries = audit.json()["entries"]
        actions = [e["details"].get("action") for e in entries]
        assert "established" in actions
        assert "removed" in actions
