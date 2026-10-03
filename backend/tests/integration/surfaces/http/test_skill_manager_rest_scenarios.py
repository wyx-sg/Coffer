"""skill-manager scenarios over REST: the unmanaged-skill routes and a skill's
reach and switch through the resource routes."""

from __future__ import annotations

import pathlib

import pytest

from tests.integration.surfaces.http.test_agent_unmanaged_skills import (
    _app,
    _client,
    _register_agent,
    _write_skill_folder,
)


@pytest.mark.acceptance(spec="skill-manager", scenario="the unmanaged-skill list holds skill rows")
def test_the_list_names_a_hand_placed_skill_and_not_a_managed_link(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59760)
    with _client(app) as c:
        uid = _register_agent(c, tmp_path)
        skills_dir = tmp_path / "agent-cfg" / "skills"
        managed = _write_skill_folder(tmp_path / "src" / "managed-one", name="managed-one")
        imported = c.post("/api/v1/skills/import", json={"path": str(managed)})
        assert imported.status_code == 201, imported.text
        assert (skills_dir / "managed-one").exists()
        loose = _write_skill_folder(skills_dir / "loose-one", name="loose-one")

        r = c.get(f"/api/v1/agents/{uid}/unmanaged-skills")

        assert r.status_code == 200, r.text
        [item] = r.json()["items"]
        assert (item["name"], item["path"], item["valid"]) == ("loose-one", str(loose), True)


@pytest.mark.acceptance(spec="skill-manager", scenario="list, adopt and delete an unmanaged skill")
def test_list_adopt_and_delete_unmanaged_skills(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59770)
    with _client(app) as c:
        uid = _register_agent(c, tmp_path)
        skills_dir = tmp_path / "agent-cfg" / "skills"
        _write_skill_folder(skills_dir / "keep-me", name="keep-me")
        _write_skill_folder(skills_dir / "junk-me", name="junk-me")
        base = f"/api/v1/agents/{uid}/unmanaged-skills"

        names = [i["name"] for i in c.get(base).json()["items"]]
        assert sorted(names) == ["junk-me", "keep-me"]

        adopted = c.post(f"{base}/keep-me/adopt", json={"location": "skills"})
        assert adopted.status_code == 201, adopted.text
        managed = c.get("/api/v1/resources", params={"kind": "skill", "name": "keep-me"})
        assert managed.json()["resources"]

        deleted = c.delete(f"{base}/junk-me", params={"location": "skills"})
        assert deleted.status_code == 204, deleted.text
        assert not (skills_dir / "junk-me").exists()
        assert c.get(base).json()["items"] == []


@pytest.mark.acceptance(
    spec="skill-manager", scenario="read an unmanaged skill's files from its reported path"
)
def test_an_unmanaged_skills_files_are_read_at_the_reported_path(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59780)
    with _client(app) as c:
        uid = _register_agent(c, tmp_path)
        skills_dir = tmp_path / "agent-cfg" / "skills"
        folder = _write_skill_folder(skills_dir / "loose-skill", name="loose-skill")
        (folder / "refs").mkdir()
        (folder / "refs" / "a.txt").write_text("alpha\n", encoding="utf-8")
        base = f"/api/v1/agents/{uid}/unmanaged-skills"

        [item] = c.get(base).json()["items"]

        assert (item["name"], item["valid"]) == ("loose-skill", True)
        root = pathlib.Path(item["path"])
        assert root.is_absolute()
        assert (root / "refs" / "a.txt").read_text(encoding="utf-8") == "alpha\n"
        # Still unmanaged: reading adopted nothing.
        assert [i["name"] for i in c.get(base).json()["items"]] == ["loose-skill"]


@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="switch and scope a skill through the resource update route",
)
def test_a_skill_is_scoped_switched_off_and_on_through_the_resource_routes(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59790)
    first_dir = tmp_path / "first-cfg"
    second_dir = tmp_path / "second-cfg"
    first_dir.mkdir()
    second_dir.mkdir()
    src = _write_skill_folder(tmp_path / "src", name="switch-me")
    with _client(app) as c:
        first = c.post("/api/v1/agents", json={"type": "claude_code", "config_dir": str(first_dir)})
        second = c.post("/api/v1/agents", json={"type": "codex", "config_dir": str(second_dir)})
        assert first.status_code == 201 and second.status_code == 201, (first.text, second.text)
        first_uid = first.json()["uid"]
        imported = c.post("/api/v1/skills/import", json={"path": str(src)})
        assert imported.status_code == 201, imported.text
        uid = imported.json()["uid"]
        first_link, second_link = (
            first_dir / "skills" / "switch-me",
            second_dir / "skills" / "switch-me",
        )
        assert first_link.exists() and second_link.exists()

        scoped = c.put(f"/api/v1/resources/{uid}/scope", json={"scope": {"agents": [first_uid]}})
        assert scoped.status_code == 200, scoped.text
        assert first_link.exists() and not second_link.exists()

        assert c.post(f"/api/v1/resources/{uid}/disable").status_code == 200
        assert not first_link.exists() and not second_link.exists()

        assert c.post(f"/api/v1/resources/{uid}/enable").status_code == 200
        assert first_link.exists() and not second_link.exists()

        trail = c.get("/api/v1/audit", params={"resource_uid": uid, "limit": 500}).json()["entries"]
        changes = [
            e["event_type"]
            for e in reversed(trail)
            if e["event_type"].startswith("resource_") and e["event_type"] != "resource_created"
        ]
        assert changes == ["resource_scope_updated", "resource_disabled", "resource_enabled"]


@pytest.mark.acceptance(spec="skill-manager", scenario="a staged archive asks before adding")
def test_a_staged_archive_adds_nothing_until_a_name_is_confirmed(tmp_path, monkeypatch):
    from coffer.infrastructure.skill.master_store import default_master_root
    from coffer.surfaces.http.skill_dependencies import get_skill_source_service
    from tests.support.skill_sources import skill_md, stage_dirs, zip_bytes

    app = _app(tmp_path, monkeypatch, 59800)
    data = zip_bytes({"review/SKILL.md": skill_md("review"), "triage/SKILL.md": skill_md("triage")})
    with _client(app) as c:
        staged = c.post(
            "/api/v1/skills/stage/archive",
            files={"file": ("skills.zip", data, "application/zip")},
        )
        assert staged.status_code == 201, staged.text
        stage = staged.json()
        assert sorted(s["name"] for s in stage["skills"]) == ["review", "triage"]
        assert not (default_master_root() / "review").exists()

        confirmed = c.post(
            f"/api/v1/skills/stage/{stage['staging_id']}/confirm", json={"skills": ["review"]}
        )

        assert confirmed.status_code == 201, confirmed.text
        assert [i["name"] for i in confirmed.json()["items"]] == ["review"]
        assert (default_master_root() / "review" / "SKILL.md").exists()
        assert not (default_master_root() / "triage").exists()
        assert stage_dirs(get_skill_source_service()) == []
