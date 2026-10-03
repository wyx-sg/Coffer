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


@pytest.mark.acceptance(
    spec="skill-manager", scenario="a skill is deleted and the agent's own folder kept"
)
def test_delete_can_keep_the_agents_own_folder(c: TestClient, tmp_path: pathlib.Path) -> None:
    _claude, claude_dir = _agent(c, tmp_path, "claude_code")
    _codex, codex_dir = _agent(c, tmp_path, "codex")
    skill = _import(c, _skill(tmp_path / "src" / "pdf", "pdf"))
    _in_the_way(codex_dir / "pdf", "codex text")

    r = c.delete(f"/api/v1/skills/{skill['uid']}", params={"keep_foreign_copies": "true"})
    assert r.status_code == 200, r.text
    [kept] = r.json()["kept_copies"]
    assert kept["path"] == str(codex_dir / "pdf") and kept["agent_name"]
    assert not (default_master_root() / "pdf").exists()
    assert not (claude_dir / "pdf").exists() and not (claude_dir / "pdf").is_symlink()
    assert "codex text" in (codex_dir / "pdf" / "SKILL.md").read_text()
    assert c.get(f"/api/v1/skills/{skill['uid']}").status_code == 404


@pytest.mark.acceptance(spec="skill-manager", scenario="a bulk delete reports each skill")
def test_bulk_delete_reports_each_skill(c: TestClient, tmp_path: pathlib.Path) -> None:
    _uid, skills_dir = _agent(c, tmp_path, "claude_code")
    pdf = _import(c, _skill(tmp_path / "src" / "pdf", "pdf"))
    notes = _import(c, _skill(tmp_path / "src" / "release-notes", "release-notes"))
    link = skills_dir / "pdf"
    _in_the_way(link, "agent text")
    uids = [pdf["uid"], notes["uid"]]

    first = c.post("/api/v1/skills/bulk-delete", json={"uids": uids})
    assert first.status_code == 200, first.text
    by_name = {r["name"]: r for r in first.json()["results"]}
    assert by_name["release-notes"]["deleted"] is True
    refused = by_name["pdf"]
    assert refused["deleted"] is False and refused["error_code"] == "SKILL_COPY_NOT_OURS"
    assert refused["error_details"]["path"] == str(link)
    assert (default_master_root() / "pdf").is_dir()

    again = c.post(
        "/api/v1/skills/bulk-delete", json={"uids": [pdf["uid"]], "keep_foreign_copies": True}
    ).json()["results"]
    assert again[0]["deleted"] is True and again[0]["kept_copies"][0]["path"] == str(link)
    assert "agent text" in (link / "SKILL.md").read_text()


@pytest.mark.acceptance(spec="skill-manager", scenario="a reach change reports delivery per agent")
def test_scope_change_reports_delivery_per_agent(c: TestClient, tmp_path: pathlib.Path) -> None:
    claude, _claude_dir = _agent(c, tmp_path, "claude_code")
    codex, codex_dir = _agent(c, tmp_path, "codex")
    skill = _import(c, _skill(tmp_path / "src" / "pdf", "pdf"))
    # Codex already holds a real folder where the link would go.
    (codex_dir / "pdf").unlink(missing_ok=True)
    _skill(codex_dir / "pdf", "pdf", "codex text")

    r = c.put(f"/api/v1/resources/{skill['uid']}/scope", json={"scope": None})
    assert r.status_code == 200, r.text
    rows = {d["agent_uid"]: d for d in r.json()["delivery"]}
    assert rows[claude]["ok"] is True and rows[claude]["reason"] is None
    assert rows[codex]["ok"] is False and rows[codex]["reason"]
    agent = c.get(f"/api/v1/resources/{claude}").json()
    assert (
        c.put(f"/api/v1/resources/{claude}/scope", json={"scope": None}).json()["delivery"] is None
    )
    assert agent["kind"] == "agent"


@pytest.mark.acceptance(
    spec="skill-manager", scenario="the read model says what state each declared tool is in"
)
def test_requires_tools_and_skills_reach_the_read_model(
    c: TestClient, tmp_path: pathlib.Path
) -> None:
    _agent_uid, _dir = _agent(c, tmp_path, "claude_code")
    _agent2, _dir2 = _agent(c, tmp_path, "codex")
    stdio = {"transport": {"type": "stdio", "command": "echo"}}
    group = {"transport": {"type": "http_api", "base_url": "https://billing.example"}}
    github = c.post(
        "/api/v1/resources", json={"kind": "mcp_server", "name": "github", "config": stdio}
    ).json()
    c.post("/api/v1/resources", json={"kind": "mcp_server", "name": "billing-api", "config": group})
    c.post(f"/api/v1/resources/{github['uid']}/disable")
    evidence = _import(c, _skill(tmp_path / "src" / "coffer-evidence", "coffer-evidence"))
    c.put(
        f"/api/v1/resources/{evidence['uid']}/scope",
        json={"scope": {"agents": [_agent_uid]}},
    )
    folder = tmp_path / "src" / "triage"
    _skill(folder, "triage")
    (folder / "SKILL.md").write_text(
        "---\nname: triage\ndescription: Triage.\nrequires:\n"
        "  tools: [github, billing-api, ghost]\nmetadata:\n  requires: [coffer-evidence]\n---\nx\n",
        encoding="utf-8",
    )
    triage = _import(c, folder)

    got = c.get(f"/api/v1/skills/{triage['uid']}").json()
    assert [(t["name"], t["kind"], t["status"]) for t in got["requires_tools"]] == [
        ("github", "mcp_server", "off"),
        ("billing-api", "custom_tools", "healthy"),
    ]
    [dep] = got["requires_skills"]
    assert dep["found"] is True and dep["uid"] == evidence["uid"]
    assert dep["delivered_to_same_agents"] is False and len(dep["missing_agent_names"]) == 1
    warnings = c.get("/api/v1/clis").json()["warnings"]
    assert any("ghost" in w["message"] and w["skill_name"] == "triage" for w in warnings)


@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="a folder whose skill is one folder down names that folder when it cannot be added",
)
def test_staging_a_folder_names_its_one_sub_folder_candidate(
    c: TestClient, tmp_path: pathlib.Path
) -> None:
    top = tmp_path / "changelog-main"
    inner = _skill(top / "skill", "changelog")
    (inner / "latest").symlink_to(tmp_path)  # leaves the folder: cannot be copied
    r = c.post("/api/v1/skills/stage/folder", json={"path": str(top)})
    assert r.status_code == 422, r.text
    details = r.json()["error"]["details"]
    assert details["candidate_folder"] == "skill"
    assert details["candidate_path"] == str(inner.resolve())
