"""The drift report's folder in the way of a delivery never made (spec
skill-manager "Report skill drift on request")."""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from tests.support.skill_sources import skill_md

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
