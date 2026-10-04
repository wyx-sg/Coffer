"""/api/v1/skills/stage/* for a folder and an archive (spec skill-manager
"Import a skill from a local path", "Add skills from an archive", "Cover skill
management on REST and the web").

A stage writes nothing: each test asserts that the master store, the resource
table and (after confirm or DELETE) the staging area are as they were.
"""

from __future__ import annotations

import io
import pathlib
import zipfile
from collections.abc import Iterator

import pytest
from starlette.testclient import TestClient

from coffer.infrastructure.skill.master_store import default_master_root
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.skill_dependencies import get_skill_source_service
from tests.support.skill_sources import skill_md, stage_dirs, symlink_zip, zip_bytes

TOKEN = "test-token-skill-sources"
ZIP = "application/zip"


@pytest.fixture
def c(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59910")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59919")
    set_active_token(TOKEN)
    with TestClient(
        create_app(), base_url="http://127.0.0.1", headers={"X-Coffer-Token": TOKEN}
    ) as client:
        yield client
    set_active_token(None)


def _user_skills(c: TestClient) -> list[str]:
    """Every skill but Coffer's own seeded one."""
    r = c.get("/api/v1/skills")
    assert r.status_code == 200, r.text
    return sorted(i["name"] for i in r.json()["items"] if i["name"] != "coffer-guide")


def _masters() -> list[str]:
    root = default_master_root()
    names = sorted(p.name for p in root.iterdir()) if root.exists() else []
    return [n for n in names if n != "coffer-guide"]


def _upload(c: TestClient, data: bytes, name: str = "skills.zip"):  # type: ignore[no-untyped-def]
    return c.post("/api/v1/skills/stage/archive", files={"file": (name, data, ZIP)})


def _nothing_written(c: TestClient) -> None:
    assert _user_skills(c) == []
    assert _masters() == []
    assert stage_dirs(get_skill_source_service()) == []


@pytest.mark.acceptance(spec="skill-manager", scenario="a folder is looked at before it is added")
def test_a_folder_is_staged_without_copying_then_added(
    c: TestClient, tmp_path: pathlib.Path
) -> None:
    folder = tmp_path / "src" / "release-notes"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(skill_md("release-notes"))
    (folder / "tool.sh").write_text("echo\n")
    r = c.post("/api/v1/skills/stage/folder", json={"path": f'  "{folder}" '})
    assert r.status_code == 201, r.text
    stage = r.json()
    assert (stage["kind"], stage["label"]) == ("folder", str(folder.resolve()))
    [found] = stage["skills"]
    assert (found["name"], found["folder"], found["file_count"], found["valid"]) == (
        "release-notes",
        ".",
        2,
        True,
    )
    assert found["description"] == "A test skill named release-notes."
    _nothing_written(c)

    r = c.post(
        f"/api/v1/skills/stage/{stage['staging_id']}/confirm", json={"skills": ["release-notes"]}
    )
    assert r.status_code == 201, r.text
    [item] = r.json()["items"]
    assert item["source"] == {"type": "local_import", "original_path": str(folder.resolve())}
    assert _user_skills(c) == ["release-notes"] and _masters() == ["release-notes"]
    r = c.post(
        f"/api/v1/skills/stage/{stage['staging_id']}/confirm", json={"skills": ["release-notes"]}
    )
    assert r.status_code == 404 and r.json()["error"]["code"] == "SKILL_STAGING_NOT_FOUND"


def test_a_folder_holding_skills_one_down_offers_each(
    c: TestClient, tmp_path: pathlib.Path
) -> None:
    for name in ("alpha", "beta"):
        (tmp_path / "pack" / name).mkdir(parents=True)
        (tmp_path / "pack" / name / "SKILL.md").write_text(skill_md(name))
    (tmp_path / "pack" / "broken").mkdir()
    (tmp_path / "pack" / "broken" / "SKILL.md").write_text("no frontmatter\n")
    r = c.post("/api/v1/skills/stage/folder", json={"path": str(tmp_path / "pack")})
    assert r.status_code == 201, r.text
    skills = {s["folder"]: s for s in r.json()["skills"]}
    assert sorted(skills) == ["alpha", "beta", "broken"]
    assert skills["broken"]["valid"] is False and skills["broken"]["name"] is None
    assert skills["broken"]["reason"]
    r = c.post(
        f"/api/v1/skills/stage/{r.json()['staging_id']}/confirm", json={"skills": ["broken"]}
    )
    assert r.status_code == 422, "an invalid skill cannot be chosen"
    _nothing_written(c)


def test_a_missing_folder_is_refused(c: TestClient, tmp_path: pathlib.Path) -> None:
    r = c.post("/api/v1/skills/stage/folder", json={"path": str(tmp_path / "absent")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "SKILL_INVALID"


@pytest.mark.acceptance(
    spec="skill-manager", scenario="a SKILL.md at the top or one folder down is found"
)
@pytest.mark.parametrize(
    ("entries", "folder"),
    [
        ({"SKILL.md": skill_md("top-skill"), "run.sh": "x"}, "."),
        ({"review/SKILL.md": skill_md("top-skill")}, "review"),
    ],
)
def test_an_archive_skill_is_found_at_the_top_or_one_down(
    c: TestClient, entries: dict[str, str], folder: str
) -> None:
    r = _upload(c, zip_bytes(entries), "one.skill")
    assert r.status_code == 201, r.text
    stage = r.json()
    assert (stage["kind"], stage["label"]) == ("archive", "one.skill")
    assert [(s["name"], s["folder"]) for s in stage["skills"]] == [("top-skill", folder)]
    assert stage_dirs(get_skill_source_service()) == [stage["staging_id"]]
    assert _user_skills(c) == [] and _masters() == []
    r = c.post(
        f"/api/v1/skills/stage/{stage['staging_id']}/confirm", json={"skills": ["top-skill"]}
    )
    assert r.status_code == 201, r.text
    assert r.json()["items"][0]["source"] == {
        "type": "archive_import",
        "archive_name": "one.skill",
        "folder": "" if folder == "." else folder,
    }
    assert stage_dirs(get_skill_source_service()) == []


@pytest.mark.acceptance(spec="skill-manager", scenario="an archive with no SKILL.md is rejected")
def test_an_archive_with_skill_md_two_down_is_rejected(c: TestClient) -> None:
    r = _upload(c, zip_bytes({"pack/review/SKILL.md": skill_md("review")}), "deep.zip")
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["code"] == "SKILL_INVALID"
    assert err["details"]["reason"] == "skill_md_not_found"
    assert err["details"]["looked_in"] == ["deep.zip/SKILL.md", "deep.zip/<folder>/SKILL.md"]
    assert "top or one folder down" in err["message"]
    _nothing_written(c)


@pytest.mark.acceptance(
    spec="skill-manager", scenario="an archive with several skills offers a choice"
)
def test_two_of_three_archive_skills_are_added(c: TestClient) -> None:
    data = zip_bytes({f"{n}/SKILL.md": skill_md(n) for n in ("review", "release", "triage")})
    stage = _upload(c, data).json()
    assert sorted(s["name"] for s in stage["skills"]) == ["release", "review", "triage"]
    r = c.post(
        f"/api/v1/skills/stage/{stage['staging_id']}/confirm", json={"skills": ["review", "triage"]}
    )
    assert r.status_code == 201, r.text
    assert sorted(i["name"] for i in r.json()["items"]) == ["review", "triage"]
    assert _user_skills(c) == ["review", "triage"]
    assert _masters() == ["review", "triage"]
    assert stage_dirs(get_skill_source_service()) == []


def _hostile(entry: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("review/SKILL.md", skill_md("review"))
        zf.writestr(zipfile.ZipInfo(entry), "x")
    return buf.getvalue()


def _too_big() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("review/SKILL.md", skill_md("review"))
        zf.writestr("review/huge.bin", b"\0" * (50 * 1024 * 1024 + 1))
    return buf.getvalue()


@pytest.mark.acceptance(
    spec="skill-manager", scenario="unsafe archive entries are rejected before anything is written"
)
@pytest.mark.parametrize(
    ("make", "entry", "problem"),
    [
        (lambda: _hostile("../evil.sh"), "../evil.sh", "parent_segment"),
        (lambda: _hostile("/tmp/evil.sh"), "/tmp/evil.sh", "absolute_path"),
        (
            lambda: symlink_zip(
                "review/link", "/etc/passwd", {"review/SKILL.md": skill_md("review")}
            ),
            "review/link",
            "symlink",
        ),
        (_too_big, "review/huge.bin", "size_limit"),
    ],
    ids=["zip-slip", "absolute", "symlink", "past-50mb"],
)
def test_an_unsafe_archive_is_rejected_naming_the_entry(
    c: TestClient,
    tmp_path: pathlib.Path,
    make,
    entry: str,
    problem: str,  # type: ignore[no-untyped-def]
) -> None:
    r = _upload(c, make())
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["code"] == "SKILL_INVALID"
    assert {"entry": entry, "problem": problem} in err["details"]["offenders"]
    assert entry in err["message"]
    _nothing_written(c)
    assert not (tmp_path / "evil.sh").exists()


@pytest.mark.acceptance(spec="skill-manager", scenario="a taken name offers replace")
def test_a_taken_name_is_refused_without_replace_and_swapped_in_place(
    c: TestClient, tmp_path: pathlib.Path
) -> None:
    cfg = tmp_path / "agent-cfg"
    cfg.mkdir()
    assert (
        c.post("/api/v1/agents", json={"type": "claude_code", "config_dir": str(cfg)}).status_code
        == 201
    )
    src = tmp_path / "src" / "review"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text(skill_md("review", "original"))
    first = c.post("/api/v1/skills/import", json={"path": str(src)}).json()
    link = cfg / "skills" / "review"
    assert link.is_symlink()

    stage = _upload(c, zip_bytes({"review/SKILL.md": skill_md("review", "replacement")})).json()
    [found] = stage["skills"]
    assert (found["name"], found["taken"], found["protected"]) == ("review", True, False)
    url = f"/api/v1/skills/stage/{stage['staging_id']}/confirm"
    r = c.post(url, json={"skills": ["review"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "RESOURCE_ALREADY_EXISTS"
    assert "original" in (default_master_root() / "review" / "SKILL.md").read_text()
    assert stage["staging_id"] in stage_dirs(get_skill_source_service()), "kept for Replace"

    r = c.post(url, json={"skills": ["review"], "replace": ["review"]})
    assert r.status_code == 201, r.text
    [item] = r.json()["items"]
    assert item["uid"] == first["uid"]
    assert item["source"]["type"] == "archive_import"
    assert [b["agent_uid"] for b in item["bindings"]] == [b["agent_uid"] for b in first["bindings"]]
    assert "replacement" in (default_master_root() / "review" / "SKILL.md").read_text()
    assert link.is_symlink() and "replacement" in (link / "SKILL.md").read_text()
    assert stage_dirs(get_skill_source_service()) == []


def test_coffers_own_skill_name_cannot_be_replaced(c: TestClient) -> None:
    stage = _upload(c, zip_bytes({"SKILL.md": skill_md("coffer-guide")})).json()
    assert stage["skills"][0]["protected"] is True
    r = c.post(
        f"/api/v1/skills/stage/{stage['staging_id']}/confirm",
        json={"skills": ["coffer-guide"], "replace": ["coffer-guide"]},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "RESOURCE_PROTECTED"


@pytest.mark.acceptance(spec="skill-manager", scenario="nothing is added until the user confirms")
def test_closing_the_dialog_removes_the_stage_and_adds_nothing(c: TestClient) -> None:
    stage = _upload(c, zip_bytes({"review/SKILL.md": skill_md("review")})).json()
    sid = stage["staging_id"]
    assert stage_dirs(get_skill_source_service()) == [sid]
    assert c.delete(f"/api/v1/skills/stage/{sid}").status_code == 204
    _nothing_written(c)
    assert c.delete(f"/api/v1/skills/stage/{sid}").status_code == 204, "idempotent"
    r = c.post(f"/api/v1/skills/stage/{sid}/confirm", json={"skills": ["review"]})
    assert r.status_code == 404 and r.json()["error"]["code"] == "SKILL_STAGING_NOT_FOUND"


def test_confirm_refuses_a_name_the_stage_did_not_find(c: TestClient) -> None:
    stage = _upload(c, zip_bytes({"review/SKILL.md": skill_md("review")})).json()
    r = c.post(f"/api/v1/skills/stage/{stage['staging_id']}/confirm", json={"skills": ["other"]})
    assert r.status_code == 422, r.text
    r = c.post(f"/api/v1/skills/stage/{stage['staging_id']}/confirm", json={"skills": []})
    assert r.status_code == 422
    assert _user_skills(c) == []
