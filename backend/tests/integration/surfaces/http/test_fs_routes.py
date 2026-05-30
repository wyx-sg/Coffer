"""HTTP coverage for /api/v1/fs/browse (spec 004-agent-registry FR-024)."""

from __future__ import annotations

import pathlib

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-fs"


def _app(tmp_path: pathlib.Path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    return create_app()


def _client(app) -> TestClient:
    set_active_token(TOKEN)
    return TestClient(app, headers={"X-Coffer-Token": TOKEN})


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="browse local folders to choose a skill directory"
)
def test_fs_browse_lists_subdirectories(tmp_path, monkeypatch):
    """GET /fs/browse returns a directory's path, parent, and immediate subdirs."""
    (tmp_path / ".codex").mkdir()
    (tmp_path / "projects").mkdir()
    (tmp_path / "note.txt").write_text("not a dir", encoding="utf-8")
    app = _app(tmp_path, monkeypatch, 59640)
    with _client(app) as c:
        r = c.get("/api/v1/fs/browse", params={"path": str(tmp_path)})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["path"] == str(tmp_path.resolve())
        assert body["parent"] == str(tmp_path.resolve().parent)
        names = {e["name"] for e in body["entries"]}
        # Hidden dirs are included (they're exactly the config folders sought)…
        assert ".codex" in names
        assert "projects" in names
        # …but files are not.
        assert "note.txt" not in names


def test_fs_browse_defaults_to_home(tmp_path, monkeypatch):
    """No `path` arg → lists the user's home directory."""
    (tmp_path / ".claude").mkdir()
    app = _app(tmp_path, monkeypatch, 59641)
    with _client(app) as c:
        r = c.get("/api/v1/fs/browse")
        assert r.status_code == 200, r.text
        assert r.json()["path"] == str(tmp_path.resolve())


def test_fs_browse_rejects_missing_path(tmp_path, monkeypatch):
    """A non-existent / non-directory path is rejected with 400."""
    app = _app(tmp_path, monkeypatch, 59642)
    with _client(app) as c:
        r = c.get("/api/v1/fs/browse", params={"path": str(tmp_path / "nope")})
        assert r.status_code == 400, r.text
        assert r.json()["error"]["code"] == "FS_PATH_NOT_BROWSABLE"
