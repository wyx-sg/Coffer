"""/api/v1/skills/stage/git and /api/v1/skills/{uid}/source/* (spec
skill-manager "Add skills from a Git repository", "Hand a Git-imported skill's
update to an agent", "Show the commands a skill declares it needs").

Every repository is a bare one under ``tmp_path`` over ``file://``.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
from collections.abc import Iterator

import pytest
from starlette.testclient import TestClient

from coffer.domain.secrets import secret_ref
from coffer.infrastructure.skill.master_store import default_master_root
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.secret_composition import get_secret_store
from coffer.surfaces.http.skill_dependencies import get_skill_source_service
from tests.support.skill_sources import Upstream, make_upstream, skill_md, stage_dirs

TOKEN = "test-token-skill-git"


@pytest.fixture
def c(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59920")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59929")
    set_active_token(TOKEN)
    with TestClient(
        create_app(), base_url="http://127.0.0.1", headers={"X-Coffer-Token": TOKEN}
    ) as client:
        yield client
    set_active_token(None)


@pytest.fixture
def up(tmp_path: pathlib.Path) -> Upstream:
    return make_upstream(
        tmp_path / "upstream",
        {"skills/review/SKILL.md": skill_md("review", "v1", requires='[jq, "gh>=2.40"]')},
    )


def _add(c: TestClient, up: Upstream, **body: str) -> dict:  # type: ignore[type-arg]
    r = c.post("/api/v1/skills/stage/git", json={"url": up.url, **body})
    assert r.status_code == 201, r.text
    stage = r.json()
    r = c.post(f"/api/v1/skills/stage/{stage['staging_id']}/confirm", json={"skills": ["review"]})
    assert r.status_code == 201, r.text
    [item] = r.json()["items"]
    return item  # type: ignore[no-any-return]


def _master() -> pathlib.Path:
    return default_master_root() / "review"


def _no_user_skill(c: TestClient) -> None:
    names = [i["name"] for i in c.get("/api/v1/skills").json()["items"]]
    assert names == ["coffer-guide"]
    assert not _master().exists()
    assert stage_dirs(get_skill_source_service()) == []


def test_a_git_stage_names_the_commit_and_confirm_records_the_source(
    c: TestClient, up: Upstream
) -> None:
    r = c.post("/api/v1/skills/stage/git", json={"url": up.url, "ref": "main", "path": "skills"})
    assert r.status_code == 201, r.text
    stage = r.json()
    assert (stage["kind"], stage["ref"], stage["subpath"], stage["commit"]) == (
        "git",
        "main",
        "skills",
        up.head(),
    )
    assert [(s["name"], s["folder"]) for s in stage["skills"]] == [("review", "review")]
    assert not _master().exists(), "staging writes nothing"
    r = c.post(f"/api/v1/skills/stage/{stage['staging_id']}/confirm", json={"skills": ["review"]})
    item = r.json()["items"][0]
    source = item["source"]
    assert (source["type"], source["url"], source["ref"], source["subpath"], source["commit"]) == (
        "git_import",
        up.url,
        "main",
        "skills/review",
        up.head(),
    )
    assert len(source["content_hash"]) == 64
    assert item["source_status"]["update_available"] is False
    assert stage_dirs(get_skill_source_service()) == []


@pytest.mark.acceptance(spec="skill-manager", scenario="a skill's requires tab links each command")
def test_requires_reaches_the_skill_read_model(c: TestClient, up: Upstream) -> None:
    item = _add(c, up, path="skills/review")
    expected = [
        {"command": "jq", "min_version": None, "profiles": []},
        {"command": "gh", "min_version": "2.40", "profiles": []},
    ]
    assert item["requires"] == expected
    assert c.get(f"/api/v1/skills/{item['uid']}").json()["requires"] == expected
    listed = {i["name"]: i for i in c.get("/api/v1/skills").json()["items"]}
    assert listed["review"]["requires"] == expected
    assert listed["coffer-guide"]["source_status"] is None


@pytest.mark.acceptance(
    spec="skill-manager", scenario="the read model says whether each declared secret is set"
)
def test_requires_secrets_reach_the_read_model_with_their_state(
    c: TestClient, tmp_path: pathlib.Path
) -> None:
    up = make_upstream(
        tmp_path / "upstream-secrets",
        {
            "skills/review/SKILL.md": skill_md(
                "review", "v1", requires="{commands: [jq], secrets: [GH_TOKEN, NPM_TOKEN]}"
            )
        },
    )
    get_secret_store().set(secret_ref("NPM_TOKEN"), "npm-value-never-served")
    item = _add(c, up, path="skills/review")
    expected = [
        {"name": "GH_TOKEN", "is_set": False, "profiles": []},
        {"name": "NPM_TOKEN", "is_set": True, "profiles": []},
    ]
    assert item["requires"] == [{"command": "jq", "min_version": None, "profiles": []}]
    assert item["requires_secrets"] == expected
    r = c.get(f"/api/v1/skills/{item['uid']}")
    assert r.json()["requires_secrets"] == expected
    assert "npm-value-never-served" not in r.text
    get_secret_store().set(secret_ref("GH_TOKEN"), "gh-value")
    listed = {i["name"]: i for i in c.get("/api/v1/skills").json()["items"]}
    assert [s["is_set"] for s in listed["review"]["requires_secrets"]] == [True, True]
    assert listed["coffer-guide"]["requires_secrets"] == []


@pytest.mark.acceptance(spec="skill-manager", scenario="an unreachable repository writes nothing")
def test_an_unreachable_url_is_502_with_gits_message(c: TestClient, tmp_path: pathlib.Path) -> None:
    r = c.post("/api/v1/skills/stage/git", json={"url": f"file://{tmp_path}/nope.git"})
    assert r.status_code == 502, r.text
    err = r.json()["error"]
    assert err["code"] == "SKILL_SOURCE_UNREACHABLE"
    assert err["message"].startswith("git clone failed:")
    assert "nope.git" in err["message"]
    _no_user_skill(c)


@pytest.mark.parametrize("url", ["ext::sh -c id", "-uhelp", "ftp://example.com/r.git"])
def test_a_transport_git_would_misread_is_422(c: TestClient, url: str) -> None:
    r = c.post("/api/v1/skills/stage/git", json={"url": url})
    assert r.status_code == 422 and r.json()["error"]["code"] == "SKILL_INVALID"
    _no_user_skill(c)


def _move(up: Upstream) -> str:
    up.write("skills/review/SKILL.md", skill_md("review", "v2"))
    up.write("skills/review/extra.txt", "x\n")
    return up.commit("v2 change")


@pytest.mark.acceptance(spec="skill-manager", scenario="a newer commit shows update available")
def test_check_reports_the_update_with_its_range_and_compare_link(
    c: TestClient, up: Upstream
) -> None:
    item = _add(c, up, path="skills/review")
    uid, first = item["uid"], item["source"]["commit"]
    new = _move(up)

    r = c.post(f"/api/v1/skills/{uid}/source/check")
    assert r.status_code == 200, r.text
    status = r.json()
    assert (status["update_available"], status["commits_ahead"], status["latest_commit"]) == (
        True,
        1,
        new,
    )
    assert status["files_changed"] == 2 and status["error"] is None
    assert [cm["subject"] for cm in status["commits"]] == ["v2 change"]
    assert status["compare_url"] is None  # a file:// repository has no host page
    listed = {i["name"]: i for i in c.get("/api/v1/skills").json()["items"]}
    assert listed["review"]["source_status"]["update_available"] is True
    assert "v1" in (_master() / "SKILL.md").read_text()
    assert c.get(f"/api/v1/skills/{uid}").json()["source"]["commit"] == first


@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="the update is offered only as a hand-off while an update is available",
)
def test_the_update_hand_off_over_rest(c: TestClient, up: Upstream) -> None:
    item = _add(c, up, path="skills/review")
    uid, first = item["uid"], item["source"]["commit"]

    # Up to date: refused, and nothing is staged.
    r = c.post(f"/api/v1/skills/{uid}/source/handoff")
    assert r.status_code == 409 and r.json()["error"]["code"] == "SKILL_UPDATE_NOT_PENDING"

    (_master() / "SKILL.md").write_text(skill_md("review", "mine"))
    new = _move(up)
    r = c.post(f"/api/v1/skills/{uid}/source/handoff")
    assert r.status_code == 200, r.text
    body = r.json()
    prompt = body["handoff"]["prompt"]
    assert body["commit"] == new
    assert str(_master()) in prompt and first in prompt and new in prompt
    assert "Files I edited since the pin: SKILL.md" in prompt and "v2 change" in prompt
    assert "mine" in (_master() / "SKILL.md").read_text()
    assert c.get(f"/api/v1/skills/{uid}").json()["source"]["commit"] == first
    assert stage_dirs(get_skill_source_service()) == []

    # The removed routes are gone.
    for method, path in (
        ("post", "preview"),
        ("get", "compare"),
        ("post", "keep"),
        ("post", "apply"),
    ):
        r = getattr(c, method)(f"/api/v1/skills/{uid}/source/{path}")
        assert r.status_code in (404, 405), (path, r.status_code)


@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="recording a merge moves the pin and keeps the merged files",
)
def test_merged_moves_the_pin_and_keeps_the_files(c: TestClient, up: Upstream) -> None:
    item = _add(c, up, path="skills/review")
    uid, first = item["uid"], item["source"]["commit"]
    (_master() / "SKILL.md").write_text(skill_md("review", "mine"))
    new = _move(up)

    # Not the update: the pinned commit is refused with a coded error.
    r = c.post(f"/api/v1/skills/{uid}/source/merged", json={"commit": first})
    assert r.status_code == 409 and r.json()["error"]["code"] == "SKILL_UPDATE_NOT_PENDING"

    r = c.post(f"/api/v1/skills/{uid}/source/merged", json={"commit": new})
    assert r.status_code == 200, r.text
    assert r.json()["source"]["commit"] == new
    assert r.json()["source_status"]["update_available"] is False
    assert "mine" in (_master() / "SKILL.md").read_text()
    audit = c.get("/api/v1/audit", params={"event_type": "skill_update_merged"}).json()
    [event] = [e for e in audit["entries"] if e["resource_name"] == "review"]
    assert (event["details"]["from_commit"], event["details"]["to_commit"]) == (first, new)
    assert stage_dirs(get_skill_source_service()) == []


@pytest.mark.acceptance(
    spec="skill-manager", scenario="the update check follows this machine's setting"
)
def test_the_update_check_setting_over_rest(c: TestClient, up: Upstream) -> None:
    config = pathlib.Path(os.environ["HOME"]) / ".coffer" / "daemon-config.json"
    assert c.get("/api/v1/skills/update-check").json() == {"interval": "6h"}
    for choice in ("1d", "7d", "manual", "6h"):
        r = c.put("/api/v1/skills/update-check", json={"interval": choice})
        assert r.status_code == 200 and r.json() == {"interval": choice}
        assert json.loads(config.read_text())["skill_update_check"] == choice
        assert c.get("/api/v1/skills/update-check").json() == {"interval": choice}
    assert c.put("/api/v1/skills/update-check", json={"interval": "hourly"}).status_code == 422
    # Check again on a skill works whatever the choice.
    item = _add(c, up, path="skills/review")
    c.put("/api/v1/skills/update-check", json={"interval": "manual"})
    assert c.post(f"/api/v1/skills/{item['uid']}/source/check").status_code == 200


def test_an_unreachable_source_on_check_is_reported_not_raised(c: TestClient, up: Upstream) -> None:
    item = _add(c, up, path="skills/review")
    uid = item["uid"]
    ok = c.post(f"/api/v1/skills/{uid}/source/check").json()
    shutil.rmtree(up.bare)
    r = c.post(f"/api/v1/skills/{uid}/source/check")
    assert r.status_code == 200, r.text
    status = r.json()
    assert status["error"].startswith("git clone failed:")
    assert status["last_success_at"] == ok["last_success_at"]
    assert status["update_available"] is False
    assert c.get(f"/api/v1/skills/{uid}").json()["source"] == item["source"]
    r = c.post(f"/api/v1/skills/{uid}/source/handoff")
    assert r.status_code == 502 and r.json()["error"]["code"] == "SKILL_SOURCE_UNREACHABLE"


def test_update_routes_refuse_a_skill_not_from_git(c: TestClient, tmp_path: pathlib.Path) -> None:
    src = tmp_path / "local" / "plain"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text(skill_md("plain"))
    uid = c.post("/api/v1/skills/import", json={"path": str(src)}).json()["uid"]
    for path in ("check", "handoff"):
        r = c.post(f"/api/v1/skills/{uid}/source/{path}")
        assert r.status_code == 409 and r.json()["error"]["code"] == "SKILL_NOT_FROM_GIT"
