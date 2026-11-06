"""The file tree of one unmanaged skill folder, which the Adopt and Delete
dialogs list: ``GET /api/v1/agents/{uid}/unmanaged-skills/{skill}/files`` (spec
skill-manager "Act on an unmanaged skill from the agent's Skills tab"). The
folder is found through the same scan the list runs; Coffer reads no file's
content and has no page for the folder.
"""

from __future__ import annotations

import os
import pathlib
import textwrap

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-unmanaged-preview"


@pytest.fixture
def client(tmp_path, monkeypatch):
    # HOME under tmp_path keeps ~/.coffer (master store, DB) off the real vault.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59940")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59949")
    set_active_token(TOKEN)
    with TestClient(create_app(), headers={"X-Coffer-Token": TOKEN}) as c:
        yield c
    set_active_token(None)


def _register_agent(c: TestClient, tmp_path: pathlib.Path) -> tuple[str, pathlib.Path]:
    agent_dir = tmp_path / "agent-cfg"
    agent_dir.mkdir(exist_ok=True)
    r = c.post(
        "/api/v1/agents",
        json={"type": "claude_code", "name": "ag", "config_dir": str(agent_dir)},
    )
    assert r.status_code == 201, r.text
    skills_dir = agent_dir / "skills"
    skills_dir.mkdir(exist_ok=True)
    return r.json()["uid"], skills_dir


def _write_skill(folder: pathlib.Path, *, name: str) -> pathlib.Path:
    (folder / "refs").mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        textwrap.dedent(
            f"""\
            ---
            name: {name}
            description: Preview test skill {name}.
            ---

            # {name} body
            """
        ),
        encoding="utf-8",
    )
    (folder / "refs" / "notes.txt").write_text("nested notes\n", encoding="utf-8")
    return folder


def _paths(node: dict) -> list[str]:  # type: ignore[type-arg]
    out = [node["path"]]
    for child in node["children"]:
        out.extend(_paths(child))
    return out


@pytest.mark.acceptance(
    spec="skill-manager", scenario="the Adopt and Delete dialogs name an unmanaged skill's files"
)
def test_the_tree_lists_the_folder_and_nothing_else_is_read(client, tmp_path):
    uid, skills_dir = _register_agent(client, tmp_path)
    folder = _write_skill(skills_dir / "loose", name="loose")
    base = f"/api/v1/agents/{uid}/unmanaged-skills/loose"

    r = client.get(f"{base}/files", params={"location": "skills"})
    assert r.status_code == 200, r.text
    root = r.json()["root"]
    assert root["abs_path"] == str(folder.resolve())
    # Directories first, then files — the managed viewer's order.
    assert _paths(root) == ["", "refs", "refs/notes.txt", "SKILL.md"]
    # No detail page and no file reads.
    assert client.get(base, params={"location": "skills"}).status_code in (404, 405)
    r = client.get(f"{base}/files/content", params={"location": "skills", "path": "SKILL.md"})
    assert r.status_code == 404
    assert (folder / "SKILL.md").read_text(encoding="utf-8").startswith("---\nname: loose")


def test_an_invalid_folder_still_lists_its_files(client, tmp_path):
    uid, skills_dir = _register_agent(client, tmp_path)
    broken = skills_dir / "broken"
    broken.mkdir()
    (broken / "README.md").write_text("no SKILL.md here\n", encoding="utf-8")
    r = client.get(
        f"/api/v1/agents/{uid}/unmanaged-skills/broken/files", params={"location": "skills"}
    )
    assert r.status_code == 200, r.text
    assert _paths(r.json()["root"]) == ["", "README.md"]


def test_the_tree_omits_a_symlink_that_escapes(client, tmp_path):
    uid, skills_dir = _register_agent(client, tmp_path)
    folder = _write_skill(skills_dir / "loose", name="loose")
    (tmp_path / "outside.txt").write_text("x", encoding="utf-8")
    os.symlink(tmp_path / "outside.txt", folder / "leak.txt")
    r = client.get(
        f"/api/v1/agents/{uid}/unmanaged-skills/loose/files", params={"location": "skills"}
    )
    assert r.status_code == 200, r.text
    assert "leak.txt" not in _paths(r.json()["root"])


@pytest.mark.parametrize("skill", ["ghost", ".system", "adopted"])
def test_an_entry_the_scan_does_not_list_is_404(client, tmp_path, skill):
    """Only a folder the list would show can be addressed: a missing name, a
    dot-entry and a Coffer-managed link are none of them unmanaged entries."""
    uid, skills_dir = _register_agent(client, tmp_path)
    _write_skill(skills_dir / "loose", name="loose")
    _write_skill(skills_dir / ".system", name="system")
    _write_skill(skills_dir / "adopted", name="adopted")
    r = client.post(
        f"/api/v1/agents/{uid}/unmanaged-skills/adopted/adopt", json={"location": "skills"}
    )
    assert r.status_code == 201, r.text
    r = client.get(
        f"/api/v1/agents/{uid}/unmanaged-skills/{skill}/files", params={"location": "skills"}
    )
    assert r.status_code == 404, r.text


def test_the_tree_at_the_wrong_or_an_unknown_location(client, tmp_path):
    uid, skills_dir = _register_agent(client, tmp_path)
    _write_skill(skills_dir / "loose", name="loose")
    base = f"/api/v1/agents/{uid}/unmanaged-skills/loose/files"
    assert client.get(base, params={"location": "agents_dir"}).status_code == 404
    assert client.get(base, params={"location": "elsewhere"}).status_code == 422
    wrong = {"X-Coffer-Token": "wrong"}
    assert client.get(base, headers=wrong, params={"location": "skills"}).status_code == 401
