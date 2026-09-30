"""/api/v1/skills/{uid}/copies/*, /api/v1/skills/orphans* and the delete refusal
(spec skill-manager "Resolve a folder in the way of a skill's link", "Refuse
deleting a skill whose copy Coffer did not make", "Act on a folder in the
skills store that no skill claims", "Say when a skill's master folder is gone").
"""

from __future__ import annotations

import pathlib
import shutil
import textwrap
from collections.abc import Iterator

import pytest
from starlette.testclient import TestClient

from coffer.infrastructure.skill.master_store import default_master_root
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-skill-copies"


def _skill(folder: pathlib.Path, name: str, body: str = "body") -> pathlib.Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        textwrap.dedent(
            f"""\
            ---
            name: {name}
            description: The {name} skill.
            ---

            {body}
            """
        ),
        encoding="utf-8",
    )
    return folder


@pytest.fixture
def c(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59940")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59949")
    set_active_token(TOKEN)
    with TestClient(create_app(), headers={"X-Coffer-Token": TOKEN}) as client:
        yield client
    set_active_token(None)


def _agent(c: TestClient, tmp_path: pathlib.Path, kind: str) -> tuple[str, pathlib.Path]:
    cfg = tmp_path / f"cfg-{kind}"
    cfg.mkdir()
    r = c.post("/api/v1/agents", json={"type": kind, "config_dir": str(cfg)})
    assert r.status_code == 201, r.text
    return r.json()["uid"], cfg / "skills"


def _import(c: TestClient, src: pathlib.Path) -> dict:  # type: ignore[type-arg]
    r = c.post("/api/v1/skills/import", json={"path": str(src)})
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def _in_the_way(link: pathlib.Path, body: str) -> None:
    """Replace Coffer's link with a real folder holding an edited copy."""
    link.unlink()
    _skill(link, link.name, body)


@pytest.mark.acceptance(
    spec="skill-manager", scenario="restoring from master backs the folder up and links it again"
)
def test_compare_then_keep_master(c: TestClient, tmp_path: pathlib.Path) -> None:
    agent_uid, skills_dir = _agent(c, tmp_path, "claude_code")
    skill = _import(c, _skill(tmp_path / "src" / "pdf", "pdf", "master text"))
    link = skills_dir / "pdf"
    _in_the_way(link, "agent text")

    entries = c.post("/api/v1/skills/verify").json()["entries"]
    assert [(e["skill_name"], e["kind"]) for e in entries] == [("pdf", "replaced_with_regular")]

    r = c.get(f"/api/v1/skills/{skill['uid']}/copies/{agent_uid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == str(link)
    assert body["kind"] == "replaced_with_regular"
    [change] = body["changes"]
    assert change["path"] == "SKILL.md" and change["status"] == "modified"
    assert "+agent text" in change["diff"] and "-master text" in change["diff"]

    r = c.post(f"/api/v1/skills/{skill['uid']}/copies/{agent_uid}/resolve", json={"keep": "master"})
    assert r.status_code == 200, r.text
    assert link.is_symlink()
    assert "master text" in (link / "SKILL.md").read_text()
    backup_root = tmp_path / ".coffer" / "content" / "backup" / "skills"
    backups = list((backup_root / "claude-code").iterdir())
    assert len(backups) == 1 and "agent text" in (backups[0] / "SKILL.md").read_text()
    assert c.post("/api/v1/skills/verify").json()["entries"] == []


@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="adopting the agent's version makes it the master for every agent",
)
def test_keep_the_agents_version(c: TestClient, tmp_path: pathlib.Path) -> None:
    agent_uid, skills_dir = _agent(c, tmp_path, "claude_code")
    _other_uid, other_dir = _agent(c, tmp_path, "codex")
    skill = _import(c, _skill(tmp_path / "src" / "pdf", "pdf", "master text"))
    _in_the_way(skills_dir / "pdf", "agent text")

    r = c.post(f"/api/v1/skills/{skill['uid']}/copies/{agent_uid}/resolve", json={"keep": "agent"})
    assert r.status_code == 200, r.text
    assert "agent text" in (default_master_root() / "pdf" / "SKILL.md").read_text()
    assert (skills_dir / "pdf").is_symlink()
    assert "agent text" in (other_dir / "pdf" / "SKILL.md").read_text()


def test_a_copy_that_is_coffers_link_has_nothing_to_resolve(
    c: TestClient, tmp_path: pathlib.Path
) -> None:
    agent_uid, _dir = _agent(c, tmp_path, "claude_code")
    skill = _import(c, _skill(tmp_path / "src" / "pdf", "pdf"))
    r = c.get(f"/api/v1/skills/{skill['uid']}/copies/{agent_uid}")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "SKILL_COPY_NOT_DIFFERING"


@pytest.mark.acceptance(
    spec="skill-manager", scenario="a folder Coffer did not make stops the delete"
)
def test_delete_refuses_when_a_copy_is_not_coffers(c: TestClient, tmp_path: pathlib.Path) -> None:
    _agent_uid, skills_dir = _agent(c, tmp_path, "claude_code")
    skill = _import(c, _skill(tmp_path / "src" / "pdf", "pdf"))
    link = skills_dir / "pdf"
    _in_the_way(link, "agent text")

    r = c.delete(f"/api/v1/skills/{skill['uid']}")
    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert err["code"] == "SKILL_COPY_NOT_OURS"
    assert err["details"]["path"] == str(link)
    assert (default_master_root() / "pdf").is_dir()
    assert c.get(f"/api/v1/skills/{skill['uid']}").status_code == 200
    assert "agent text" in (link / "SKILL.md").read_text()


@pytest.mark.acceptance(
    spec="skill-manager", scenario="an orphan folder is added in place or moved out"
)
def test_orphans_list_adopt_and_remove(c: TestClient, tmp_path: pathlib.Path) -> None:
    root = default_master_root()
    _skill(root / "lint-rules", "lint-rules")
    (root / "lint-rules" / "rules.md").write_text("x")
    _skill(root / "old-notes", "old-notes")

    items = {i["name"]: i for i in c.get("/api/v1/skills/orphans").json()["items"]}
    assert set(items) == {"lint-rules", "old-notes"}
    assert items["lint-rules"]["valid"] is True
    assert items["lint-rules"]["file_count"] == 2

    r = c.post("/api/v1/skills/orphans/lint-rules/adopt")
    assert r.status_code == 201, r.text
    assert r.json()["name"] == "lint-rules"
    names = [i["name"] for i in c.get("/api/v1/skills").json()["items"]]
    assert "lint-rules" in names

    assert c.delete("/api/v1/skills/orphans/old-notes").status_code == 204
    assert not (root / "old-notes").exists()
    assert list((tmp_path / ".coffer" / "content" / "backup" / "skills" / "orphans").iterdir())
    assert c.get("/api/v1/skills/orphans").json()["items"] == []
    # A claimed folder is no orphan.
    r = c.delete("/api/v1/skills/orphans/lint-rules")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "SKILL_ORPHAN_NOT_FOUND"


@pytest.mark.acceptance(spec="skill-manager", scenario="a skill whose master is gone says so")
def test_master_missing_is_on_the_read_model(c: TestClient, tmp_path: pathlib.Path) -> None:
    skill = _import(c, _skill(tmp_path / "src" / "pdf", "pdf"))
    assert skill["master_missing"] is False
    shutil.rmtree(default_master_root() / "pdf")
    assert c.get(f"/api/v1/skills/{skill['uid']}").json()["master_missing"] is True
