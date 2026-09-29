"""HTTP coverage for the read-only unmanaged-skill preview routes.

``GET /api/v1/agents/{uid}/unmanaged-skills/{skill}``, ``.../files`` and
``.../files/content`` — spec skill-manager "Preview an unmanaged skill
read-only". The folder is found through the same scan the list runs, and file
reads reuse the managed viewer's containment guard, so a path that leaves the
folder is refused before anything is read.
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
    spec="skill-manager", scenario="preview an unmanaged skill's metadata and files"
)
def test_preview_returns_metadata_tree_and_content(client, tmp_path):
    uid, skills_dir = _register_agent(client, tmp_path)
    folder = _write_skill(skills_dir / "loose", name="loose")
    base = f"/api/v1/agents/{uid}/unmanaged-skills/loose"

    r = client.get(base, params={"location": "skills"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {
        "name": "loose",
        "path": str(folder),
        "location": "skills",
        "valid": True,
        "reason": None,
        "foreign_link": False,
        "description": "Preview test skill loose.",
    }

    r = client.get(f"{base}/files", params={"location": "skills"})
    assert r.status_code == 200, r.text
    root = r.json()["root"]
    assert root["abs_path"] == str(folder.resolve())
    # Directories first, then files — the managed viewer's order.
    assert _paths(root) == ["", "refs", "refs/notes.txt", "SKILL.md"]

    r = client.get(f"{base}/files/content", params={"location": "skills", "path": "SKILL.md"})
    assert r.status_code == 200, r.text
    content = r.json()
    assert "# loose body" in content["content"]
    assert content["binary"] is False
    assert content["truncated"] is False
    assert content["abs_path"] == str((folder / "SKILL.md").resolve())
    # Read-only: the folder is untouched by the preview.
    assert (folder / "SKILL.md").read_text(encoding="utf-8").startswith("---\nname: loose")


@pytest.mark.acceptance(
    spec="skill-manager", scenario="an invalid unmanaged skill still opens and says why"
)
def test_preview_of_invalid_folder_carries_reason_and_files(client, tmp_path):
    uid, skills_dir = _register_agent(client, tmp_path)
    broken = skills_dir / "broken"
    broken.mkdir()
    (broken / "README.md").write_text("no SKILL.md here\n", encoding="utf-8")
    base = f"/api/v1/agents/{uid}/unmanaged-skills/broken"

    r = client.get(base, params={"location": "skills"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["valid"] is False
    assert body["reason"]
    assert body["description"] is None

    r = client.get(f"{base}/files", params={"location": "skills"})
    assert r.status_code == 200, r.text
    assert _paths(r.json()["root"]) == ["", "README.md"]


def test_preview_binary_file_is_flagged_with_empty_content(client, tmp_path):
    uid, skills_dir = _register_agent(client, tmp_path)
    folder = _write_skill(skills_dir / "bin", name="bin")
    (folder / "blob.bin").write_bytes(b"\x00\x01\x02")
    r = client.get(
        f"/api/v1/agents/{uid}/unmanaged-skills/bin/files/content",
        params={"location": "skills", "path": "blob.bin"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["binary"] is True
    assert r.json()["content"] == ""
    assert r.json()["size"] == 3


@pytest.mark.acceptance(
    spec="skill-manager", scenario="reject reading a path outside an unmanaged skill folder"
)
@pytest.mark.parametrize("kind", ["dotdot", "absolute", "symlink"])
def test_preview_refuses_a_path_that_leaves_the_folder(client, tmp_path, kind):
    uid, skills_dir = _register_agent(client, tmp_path)
    folder = _write_skill(skills_dir / "loose", name="loose")
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET", encoding="utf-8")
    # A sibling folder the ``..`` path aims at, to prove the escape is refused
    # rather than merely not found.
    _write_skill(skills_dir / "other", name="other")
    if kind == "dotdot":
        path = "../other/SKILL.md"
    elif kind == "absolute":
        path = str(secret)
    else:
        os.symlink(secret, folder / "leak.txt")
        path = "leak.txt"

    r = client.get(
        f"/api/v1/agents/{uid}/unmanaged-skills/loose/files/content",
        params={"location": "skills", "path": path},
    )
    assert r.status_code == 400, r.text
    assert "TOP SECRET" not in r.text
    assert "Preview test skill other" not in r.text


def test_preview_tree_omits_a_symlink_that_escapes(client, tmp_path):
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
def test_preview_of_an_entry_the_scan_does_not_list_is_404(client, tmp_path, skill):
    """Only a folder the list would show can be addressed: a missing name, a
    dot-entry and a Coffer-managed link all exist on disk or not, but none is
    an unmanaged entry, so each is not found."""
    uid, skills_dir = _register_agent(client, tmp_path)
    _write_skill(skills_dir / "loose", name="loose")
    _write_skill(skills_dir / ".system", name="system")
    _write_skill(skills_dir / "adopted", name="adopted")
    r = client.post(
        f"/api/v1/agents/{uid}/unmanaged-skills/adopted/adopt", json={"location": "skills"}
    )
    assert r.status_code == 201, r.text
    assert (skills_dir / "adopted").is_symlink()
    for suffix in ("", "/files"):
        r = client.get(
            f"/api/v1/agents/{uid}/unmanaged-skills/{skill}{suffix}",
            params={"location": "skills"},
        )
        assert r.status_code == 404, (suffix, r.text)


def test_preview_at_the_wrong_location_is_404(client, tmp_path):
    uid, skills_dir = _register_agent(client, tmp_path)
    _write_skill(skills_dir / "loose", name="loose")
    r = client.get(
        f"/api/v1/agents/{uid}/unmanaged-skills/loose", params={"location": "agents_dir"}
    )
    assert r.status_code == 404, r.text


def test_preview_rejects_an_unknown_location_and_missing_file(client, tmp_path):
    uid, skills_dir = _register_agent(client, tmp_path)
    _write_skill(skills_dir / "loose", name="loose")
    base = f"/api/v1/agents/{uid}/unmanaged-skills/loose"
    assert client.get(base, params={"location": "elsewhere"}).status_code == 422
    assert client.get(base).status_code == 422
    r = client.get(f"{base}/files/content", params={"location": "skills", "path": "nope.md"})
    assert r.status_code == 404, r.text


def test_preview_of_an_unknown_agent_is_404(client):
    r = client.get(
        f"/api/v1/agents/{'0' * 32}/unmanaged-skills/loose", params={"location": "skills"}
    )
    assert r.status_code == 404, r.text


def test_preview_requires_the_token(client, tmp_path):
    uid, skills_dir = _register_agent(client, tmp_path)
    _write_skill(skills_dir / "loose", name="loose")
    r = client.get(
        f"/api/v1/agents/{uid}/unmanaged-skills/loose",
        params={"location": "skills"},
        headers={"X-Coffer-Token": "wrong"},
    )
    assert r.status_code == 401
