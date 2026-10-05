"""POST /api/v1/skills/conformance/handoff and ``requires_declared`` (spec
skill-manager "Hand a skill's review to an agent", "Tell a skill that declares
nothing from one that has not declared")."""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest
from starlette.testclient import TestClient

from coffer.infrastructure.skill.master_store import default_master_root
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from tests.support.skill_sources import Upstream, make_upstream, skill_md

TOKEN = "test-token-skill-conformance"


@pytest.fixture
def c(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59930")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59939")
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
        {
            "skills/bare/SKILL.md": skill_md("bare", "v1"),
            "skills/empty/SKILL.md": skill_md("empty", "v1", requires="[]"),
        },
    )


def _add(c: TestClient, up: Upstream) -> dict[str, dict]:  # type: ignore[type-arg]
    r = c.post("/api/v1/skills/stage/git", json={"url": up.url, "path": "skills"})
    assert r.status_code == 201, r.text
    r = c.post(
        f"/api/v1/skills/stage/{r.json()['staging_id']}/confirm",
        json={"skills": ["bare", "empty"]},
    )
    assert r.status_code == 201, r.text
    return {i["name"]: i for i in r.json()["items"]}


def test_the_read_model_tells_undeclared_from_declared(c: TestClient, up: Upstream) -> None:
    items = _add(c, up)
    assert items["bare"]["requires_declared"] is False
    assert items["empty"]["requires_declared"] is True
    folder = default_master_root() / "bare"
    (folder / "profiles").mkdir()
    (folder / "profiles" / "p.md").write_text("---\nrequires: [jq]\n---\n")
    got = c.get(f"/api/v1/skills/{items['bare']['uid']}").json()
    assert got["requires_declared"] is True


def test_the_prompt_is_built_from_the_folders_as_they_are(c: TestClient, up: Upstream) -> None:
    items = _add(c, up)
    r = c.post(
        "/api/v1/skills/conformance/handoff",
        json={"uids": [items["bare"]["uid"], items["empty"]["uid"]]},
    )
    assert r.status_code == 200, r.text
    prompt = r.json()["prompt"]
    assert str(default_master_root() / "bare") in prompt
    assert "bare — declaration: none yet" in prompt
    assert "empty — declaration: present" in prompt
    assert "kept across updates" in prompt
    one = c.post(
        "/api/v1/skills/conformance/handoff", json={"uids": [items["empty"]["uid"]]}
    ).json()["prompt"]
    assert "Skill: empty" in one


def test_an_unknown_uid_is_404_and_no_uids_is_422(c: TestClient) -> None:
    assert c.post("/api/v1/skills/conformance/handoff", json={"uids": ["nope"]}).status_code == 404
    assert c.post("/api/v1/skills/conformance/handoff", json={"uids": []}).status_code == 422
