"""HTTP coverage for the read-only skill file viewer (spec 005-skill-manager).

Boots the app exactly like ``test_skill_routes.py``: a temp ``HOME`` so the
master store lands under ``tmp_path/.coffer/skills`` and a temp SQLite DB.
Imports a skill with a nested folder, then exercises the two new endpoints:

- ``GET /skills/{name}/files`` — tree shape
- ``GET /skills/{name}/files/content`` — single-file read, path-escape
  rejection, binary detection, oversize truncation.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest
from starlette.testclient import TestClient

from coffer.application.skill.file_ops import MAX_FILE_BYTES
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-files"


def _app(tmp_path: pathlib.Path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    return create_app()


def _client(app) -> TestClient:
    set_active_token(TOKEN)
    return TestClient(app, headers={"X-Coffer-Token": TOKEN})


def _write_nested_skill_folder(folder: pathlib.Path, *, name: str) -> pathlib.Path:
    """A valid skill with a nested subdir and an extra file inside it."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        textwrap.dedent(
            f"""\
            ---
            name: {name}
            description: A test skill named {name}.
            ---

            # body

            hello
            """
        ),
        encoding="utf-8",
    )
    scripts = folder / "scripts"
    scripts.mkdir()
    (scripts / "run.py").write_text("print('hi')\n", encoding="utf-8")
    return folder


def _import(c: TestClient, src: pathlib.Path) -> dict:
    r = c.post("/api/v1/skills/import", json={"path": str(src)})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.acceptance(spec="005-skill-manager", scenario="view a skill's files as a tree")
def test_list_skill_files_returns_tree(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59700)
    src = tmp_path / "src"
    _write_nested_skill_folder(src, name="tree-skill")

    with _client(app) as c:
        _import(c, src)

        r = c.get("/api/v1/skills/tree-skill/files")
        assert r.status_code == 200, r.text
        root = r.json()["root"]
        assert root["type"] == "dir"
        assert root["path"] == ""

        names = {child["name"]: child for child in root["children"]}
        # Both the imported tree and the master store's provenance file appear.
        assert "SKILL.md" in names
        assert "scripts" in names

        # Directories sort before files within a level.
        types = [child["type"] for child in root["children"]]
        assert types == sorted(types, key=lambda t: t != "dir")

        # The scripts dir is recursive and carries its nested file with a
        # POSIX relative path + byte size.
        scripts = names["scripts"]
        assert scripts["type"] == "dir"
        run = next(c for c in scripts["children"] if c["name"] == "run.py")
        assert run["type"] == "file"
        assert run["path"] == "scripts/run.py"
        assert run["size"] == len("print('hi')\n")

        # A regular file records its size; directories carry none.
        skill_md = names["SKILL.md"]
        assert skill_md["type"] == "file"
        assert skill_md["size"] > 0
        assert scripts["size"] is None


@pytest.mark.acceptance(spec="005-skill-manager", scenario="view a single skill file's contents")
def test_read_single_skill_file(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59710)
    src = tmp_path / "src"
    _write_nested_skill_folder(src, name="read-skill")

    with _client(app) as c:
        _import(c, src)

        r = c.get(
            "/api/v1/skills/read-skill/files/content",
            params={"path": "scripts/run.py"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["path"] == "scripts/run.py"
        assert body["content"] == "print('hi')\n"
        assert body["binary"] is False
        assert body["truncated"] is False
        assert body["size"] == len("print('hi')\n")

    # A file that does not exist in the skill is a 404.
    with _client(app) as c:
        r = c.get(
            "/api/v1/skills/read-skill/files/content",
            params={"path": "scripts/missing.py"},
        )
        assert r.status_code == 404, r.text
        assert r.json()["error"]["code"]


@pytest.mark.acceptance(
    spec="005-skill-manager", scenario="reject reading a path outside the skill folder"
)
def test_reject_path_escape(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59720)
    src = tmp_path / "src"
    _write_nested_skill_folder(src, name="escape-skill")

    with _client(app) as c:
        _import(c, src)

        # Relative traversal out of the master folder.
        r = c.get(
            "/api/v1/skills/escape-skill/files/content",
            params={"path": "../../etc/passwd"},
        )
        assert r.status_code == 400, r.text
        body = r.json()
        assert "error" in body
        assert isinstance(body["error"].get("code"), str) and body["error"]["code"]

        # An absolute path is likewise rejected (it resolves outside root).
        r = c.get(
            "/api/v1/skills/escape-skill/files/content",
            params={"path": "/etc/passwd"},
        )
        assert r.status_code == 400, r.text


def test_files_endpoints_404_for_unknown_skill(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59730)
    with _client(app) as c:
        r = c.get("/api/v1/skills/nope/files")
        assert r.status_code == 404, r.text
        r = c.get("/api/v1/skills/nope/files/content", params={"path": "SKILL.md"})
        assert r.status_code == 404, r.text


def test_binary_file_returns_binary_true(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59740)
    src = tmp_path / "src"
    _write_nested_skill_folder(src, name="bin-skill")
    # A NUL byte makes the file binary; written into the source before import.
    (src / "blob.bin").write_bytes(b"\x00\x01\x02PNG\x00")

    with _client(app) as c:
        _import(c, src)
        r = c.get(
            "/api/v1/skills/bin-skill/files/content",
            params={"path": "blob.bin"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["binary"] is True
        assert body["content"] == ""
        assert body["size"] == len(b"\x00\x01\x02PNG\x00")


def test_oversize_file_is_truncated(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59750)
    src = tmp_path / "src"
    _write_nested_skill_folder(src, name="big-skill")
    big = "a" * (MAX_FILE_BYTES + 1024)
    (src / "big.txt").write_text(big, encoding="utf-8")

    with _client(app) as c:
        _import(c, src)
        r = c.get(
            "/api/v1/skills/big-skill/files/content",
            params={"path": "big.txt"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["truncated"] is True
        assert body["binary"] is False
        # Content is capped at the byte limit; size reports the true length.
        assert len(body["content"]) == MAX_FILE_BYTES
        assert body["size"] == len(big)
