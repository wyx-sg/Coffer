"""HTTP coverage for /api/v1/agents/{name}/unmanaged-skills and
follow-policy fields on PATCH /api/v1/agents/{name} (spec 005 FR-022/023/025).
"""

from __future__ import annotations

import pathlib
import textwrap

from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-unmanaged"


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
    """Write a valid SKILL.md so the folder passes validation."""
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


def _register_agent(c: TestClient, tmp_path: pathlib.Path) -> str:
    """Register a claude_code agent 'ag' with a local config_dir and return its name."""
    agent_dir = tmp_path / "agent-cfg"
    agent_dir.mkdir(exist_ok=True)
    r = c.post(
        "/api/v1/agents",
        json={"type": "claude_code", "name": "ag", "config_dir": str(agent_dir)},
    )
    assert r.status_code == 201, r.text
    return "ag"


# ---------------------------------------------------------------------------
# list unmanaged skills
# ---------------------------------------------------------------------------


def test_list_unmanaged_returns_valid_skill(tmp_path, monkeypatch):
    """A skill folder placed directly in <config_dir>/skills is listed as valid."""
    app = _app(tmp_path, monkeypatch, 59970)
    with _client(app) as c:
        name = _register_agent(c, tmp_path)
        skills_dir = tmp_path / "agent-cfg" / "skills"
        _write_skill_folder(skills_dir / "my-skill", name="my-skill")

        r = c.get(f"/api/v1/agents/{name}/unmanaged-skills")
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert len(items) == 1
        item = items[0]
        assert item["name"] == "my-skill"
        assert item["valid"] is True
        assert item["reason"] is None
        assert item["foreign_link"] is False
        assert item["location"] == "skills"


def test_list_unmanaged_excludes_managed_link(tmp_path, monkeypatch):
    """A skill adopted into the master store appears as managed, not unmanaged."""
    app = _app(tmp_path, monkeypatch, 59980)
    with _client(app) as c:
        name = _register_agent(c, tmp_path)
        skills_dir = tmp_path / "agent-cfg" / "skills"

        # Place two unmanaged folders; adopt one of them.
        _write_skill_folder(skills_dir / "skill-a", name="skill-a")
        _write_skill_folder(skills_dir / "skill-b", name="skill-b")

        r = c.post(
            f"/api/v1/agents/{name}/unmanaged-skills/skill-a/adopt",
            json={"location": "skills"},
        )
        assert r.status_code == 201, r.text

        # Only skill-b should appear as unmanaged now.
        r = c.get(f"/api/v1/agents/{name}/unmanaged-skills")
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        names = [i["name"] for i in items]
        assert "skill-a" not in names
        assert "skill-b" in names


# ---------------------------------------------------------------------------
# adopt unmanaged skill
# ---------------------------------------------------------------------------


def test_adopt_unmanaged_skill_201(tmp_path, monkeypatch):
    """Adopting an unmanaged skill creates a master copy and a managed symlink."""
    app = _app(tmp_path, monkeypatch, 59990)
    with _client(app) as c:
        name = _register_agent(c, tmp_path)
        skills_dir = tmp_path / "agent-cfg" / "skills"
        _write_skill_folder(skills_dir / "skill-x", name="skill-x")

        r = c.post(
            f"/api/v1/agents/{name}/unmanaged-skills/skill-x/adopt",
            json={"location": "skills"},
        )
        assert r.status_code == 201, r.text
        assert r.json()["name"] == "skill-x"

        # The original folder is gone; a managed symlink replaced it.
        link_path = skills_dir / "skill-x"
        assert link_path.is_symlink(), "original should be replaced with a symlink"

        # The skill appears in the global skills list.
        r = c.get("/api/v1/skills")
        assert r.status_code == 200, r.text
        names = [s["name"] for s in r.json()["items"]]
        assert "skill-x" in names


def test_adopt_invalid_skill_422(tmp_path, monkeypatch):
    """Adopting a folder without SKILL.md returns 422 UNMANAGED_SKILL_INVALID."""
    app = _app(tmp_path, monkeypatch, 60000)
    with _client(app) as c:
        name = _register_agent(c, tmp_path)
        skills_dir = tmp_path / "agent-cfg" / "skills"
        # Create a folder WITHOUT SKILL.md.
        bad = skills_dir / "bad-skill"
        bad.mkdir(parents=True)

        r = c.post(
            f"/api/v1/agents/{name}/unmanaged-skills/bad-skill/adopt",
            json={"location": "skills"},
        )
        assert r.status_code == 422, r.text
        assert r.json()["error"]["code"] == "UNMANAGED_SKILL_INVALID"


# ---------------------------------------------------------------------------
# delete unmanaged skill
# ---------------------------------------------------------------------------


def test_delete_unmanaged_skill_204(tmp_path, monkeypatch):
    """DELETE removes the unmanaged folder from disk."""
    app = _app(tmp_path, monkeypatch, 60010)
    with _client(app) as c:
        name = _register_agent(c, tmp_path)
        skills_dir = tmp_path / "agent-cfg" / "skills"
        _write_skill_folder(skills_dir / "del-me", name="del-me")

        r = c.delete(
            f"/api/v1/agents/{name}/unmanaged-skills/del-me",
            params={"location": "skills"},
        )
        assert r.status_code == 204, r.text
        assert not (skills_dir / "del-me").exists()


# ---------------------------------------------------------------------------
# 404 paths
# ---------------------------------------------------------------------------


def test_list_unmanaged_unknown_agent_404(tmp_path, monkeypatch):
    """Listing unmanaged skills for an unknown agent returns 404."""
    app = _app(tmp_path, monkeypatch, 60020)
    with _client(app) as c:
        r = c.get("/api/v1/agents/ghost/unmanaged-skills")
        assert r.status_code == 404, r.text


def test_adopt_unknown_skill_404(tmp_path, monkeypatch):
    """Adopting a non-existent skill name returns 404 UNMANAGED_SKILL_NOT_FOUND."""
    app = _app(tmp_path, monkeypatch, 60030)
    with _client(app) as c:
        _register_agent(c, tmp_path)

        r = c.post(
            "/api/v1/agents/ag/unmanaged-skills/no-such-skill/adopt",
            json={"location": "skills"},
        )
        assert r.status_code == 404, r.text
        assert r.json()["error"]["code"] == "UNMANAGED_SKILL_NOT_FOUND"


def test_delete_unknown_skill_404(tmp_path, monkeypatch):
    """Deleting a non-existent unmanaged skill returns 404 UNMANAGED_SKILL_NOT_FOUND."""
    app = _app(tmp_path, monkeypatch, 60040)
    with _client(app) as c:
        _register_agent(c, tmp_path)

        r = c.delete(
            "/api/v1/agents/ag/unmanaged-skills/no-such-skill",
            params={"location": "skills"},
        )
        assert r.status_code == 404, r.text
        assert r.json()["error"]["code"] == "UNMANAGED_SKILL_NOT_FOUND"


# ---------------------------------------------------------------------------
# PATCH /api/v1/agents/{name} — follow-policy fields
# ---------------------------------------------------------------------------


def test_patch_follow_all_skills_false(tmp_path, monkeypatch):
    """PATCH with follow_all_skills=false is persisted and reflected in AgentOut."""
    app = _app(tmp_path, monkeypatch, 60050)
    with _client(app) as c:
        name = _register_agent(c, tmp_path)

        # Default should be true after registration.
        r = c.get(f"/api/v1/agents/{name}")
        assert r.status_code == 200, r.text
        assert r.json()["follow_all_skills"] is True

        # Disable follow.
        r = c.patch(f"/api/v1/agents/{name}", json={"follow_all_skills": False})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["follow_all_skills"] is False
        # skill_exclusions unchanged.
        assert body["skill_exclusions"] == []

        # Verify GET returns updated value.
        r = c.get(f"/api/v1/agents/{name}")
        assert r.status_code == 200, r.text
        assert r.json()["follow_all_skills"] is False


def test_patch_skill_exclusions_roundtrip(tmp_path, monkeypatch):
    """PATCH with skill_exclusions list is persisted and reflected in AgentOut."""
    app = _app(tmp_path, monkeypatch, 60060)
    with _client(app) as c:
        name = _register_agent(c, tmp_path)

        r = c.patch(f"/api/v1/agents/{name}", json={"skill_exclusions": ["x", "y"]})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["skill_exclusions"] == ["x", "y"]
        # follow_all_skills should be untouched (still true).
        assert body["follow_all_skills"] is True

        # Round-trip via GET.
        r = c.get(f"/api/v1/agents/{name}")
        assert r.status_code == 200, r.text
        assert r.json()["skill_exclusions"] == ["x", "y"]
