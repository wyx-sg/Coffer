"""/api/v1/skills/{uid}/source/change (spec skill-manager "Change a
Git-imported skill's source") and the drift report's folder in the way of a
delivery never made (spec skill-manager "Report skill drift on request")."""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest
from starlette.testclient import TestClient

from coffer.infrastructure.skill.master_store import default_master_root
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.skill_dependencies import get_skill_source_service
from tests.support.skill_sources import make_upstream, skill_md, stage_dirs

TOKEN = "test-token-skill-change"


@pytest.fixture
def c(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59950")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59959")
    set_active_token(TOKEN)
    with TestClient(
        create_app(), base_url="http://127.0.0.1", headers={"X-Coffer-Token": TOKEN}
    ) as client:
        yield client
    set_active_token(None)


def _add(c: TestClient, url: str, path: str) -> dict:  # type: ignore[type-arg]
    stage = c.post("/api/v1/skills/stage/git", json={"url": url, "path": path}).json()
    r = c.post(f"/api/v1/skills/stage/{stage['staging_id']}/confirm", json={"skills": ["review"]})
    assert r.status_code == 201, r.text
    return r.json()["items"][0]  # type: ignore[no-any-return]


@pytest.mark.acceptance(
    spec="skill-manager", scenario="a new source is shown against the current version first"
)
def test_change_source_names_the_files_then_applies(c: TestClient, tmp_path: pathlib.Path) -> None:
    old = make_upstream(tmp_path / "old", {"skills/review/SKILL.md": skill_md("review", "v1")})
    new = make_upstream(tmp_path / "new", {"team/review/SKILL.md": skill_md("review", "team")})
    item = _add(c, old.url, "skills/review")

    r = c.post(
        f"/api/v1/skills/{item['uid']}/source/change",
        json={"url": new.url, "ref": "main", "path": "team/review"},
    )
    assert r.status_code == 200, r.text
    p = r.json()
    assert set(p) == {"staging_id", "commit", "files"}  # names only, no diff text
    assert p["commit"] == new.head()
    assert p["files"] == [{"path": "SKILL.md", "status": "modified"}]
    assert "v1" in (default_master_root() / "review" / "SKILL.md").read_text()

    r = c.post(
        f"/api/v1/skills/{item['uid']}/source/change/apply", json={"staging_id": p["staging_id"]}
    )
    assert r.status_code == 200, r.text
    source = r.json()["source"]
    assert (source["url"], source["subpath"], source["commit"]) == (
        new.url,
        "team/review",
        new.head(),
    )
    assert "team" in (default_master_root() / "review" / "SKILL.md").read_text()
    assert stage_dirs(get_skill_source_service()) == []
    audit = c.get("/api/v1/audit", params={"event_type": "skill_updated"}).json()
    assert [e["resource_name"] for e in audit["entries"]] == ["review"]


def test_cancelling_a_source_change_leaves_the_skill_and_a_gone_stage_is_refused(
    c: TestClient, tmp_path: pathlib.Path
) -> None:
    old = make_upstream(tmp_path / "old", {"skills/review/SKILL.md": skill_md("review", "v1")})
    new = make_upstream(tmp_path / "new", {"SKILL.md": skill_md("review", "team")})
    item = _add(c, old.url, "skills/review")
    uid = item["uid"]
    p = c.post(f"/api/v1/skills/{uid}/source/change", json={"url": new.url}).json()
    assert c.delete(f"/api/v1/skills/stage/{p['staging_id']}").status_code == 204
    assert stage_dirs(get_skill_source_service()) == []
    assert c.get(f"/api/v1/skills/{uid}").json()["source"]["url"] == old.url
    r = c.post(f"/api/v1/skills/{uid}/source/change/apply", json={"staging_id": p["staging_id"]})
    assert r.status_code == 404 and r.json()["error"]["code"] == "SKILL_STAGING_NOT_FOUND"
    assert "v1" in (default_master_root() / "review" / "SKILL.md").read_text()


def test_a_stage_of_another_skill_is_refused(c: TestClient, tmp_path: pathlib.Path) -> None:
    old = make_upstream(tmp_path / "old", {"skills/review/SKILL.md": skill_md("review", "v1")})
    other = make_upstream(tmp_path / "other", {"SKILL.md": skill_md("lint", "x")})
    new = make_upstream(tmp_path / "new", {"SKILL.md": skill_md("review", "team")})
    review = _add(c, old.url, "skills/review")
    lint_stage = c.post("/api/v1/skills/stage/git", json={"url": other.url}).json()
    lint = c.post(
        f"/api/v1/skills/stage/{lint_stage['staging_id']}/confirm", json={"skills": ["lint"]}
    ).json()["items"][0]
    p = c.post(f"/api/v1/skills/{review['uid']}/source/change", json={"url": new.url}).json()
    r = c.post(
        f"/api/v1/skills/{lint['uid']}/source/change/apply", json={"staging_id": p["staging_id"]}
    )
    assert r.status_code == 422, r.text
    assert "v1" in (default_master_root() / "review" / "SKILL.md").read_text()


def test_a_source_naming_another_skill_is_refused(c: TestClient, tmp_path: pathlib.Path) -> None:
    old = make_upstream(tmp_path / "old", {"skills/review/SKILL.md": skill_md("review", "v1")})
    other = make_upstream(tmp_path / "other", {"SKILL.md": skill_md("lint", "x")})
    item = _add(c, old.url, "skills/review")
    r = c.post(f"/api/v1/skills/{item['uid']}/source/change", json={"url": other.url})
    assert r.status_code == 422, r.text
    assert c.get(f"/api/v1/skills/{item['uid']}").json()["source"]["url"] == old.url
    assert stage_dirs(get_skill_source_service()) == []


@pytest.mark.acceptance(
    spec="skill-manager", scenario="a folder in the way of a first delivery is reported"
)
def test_a_folder_blocking_a_first_delivery_is_drift(c: TestClient, tmp_path: pathlib.Path) -> None:
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    assert (
        c.post("/api/v1/agents", json={"type": "claude_code", "config_dir": str(cfg)}).status_code
        == 201
    )
    blocker = cfg / "skills" / "review"
    blocker.mkdir(parents=True)
    (blocker / "SKILL.md").write_text(skill_md("review", "mine"))
    src = tmp_path / "src" / "review"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text(skill_md("review", "theirs"))
    assert c.post("/api/v1/skills/import", json={"path": str(src)}).status_code == 201
    entries = c.post("/api/v1/skills/verify").json()["entries"]
    assert [(e["skill_name"], e["kind"], e["target_path"]) for e in entries] == [
        ("review", "replaced_with_regular", str(blocker))
    ]
    assert "mine" in (blocker / "SKILL.md").read_text()
