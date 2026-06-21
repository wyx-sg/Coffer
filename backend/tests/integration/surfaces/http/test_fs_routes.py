"""HTTP coverage for /api/v1/fs/* (spec 004-agent-registry FR-024/FR-039/FR-042)."""

from __future__ import annotations

import pathlib
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from coffer.application.fs import editor_service, open_service, pick_service
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
    spec="004-agent-registry", scenario="browse local folders to choose a config dir"
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


def _capture_spawn(monkeypatch, platform: str = "darwin") -> list[list[str]]:
    """Pin the platform and capture launcher argv instead of spawning a process."""
    calls: list[list[str]] = []
    monkeypatch.setattr("sys.platform", platform)
    monkeypatch.setattr(open_service.subprocess, "Popen", lambda cmd, **_: calls.append(cmd))
    return calls


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="open a managed file via the daemon (web open/reveal)"
)
def test_fs_open_launches_default_app(tmp_path, monkeypatch):
    """POST /fs/open with no editor → OS default launcher, 204."""
    f = tmp_path / "settings.json"
    f.write_text("{}", encoding="utf-8")
    calls = _capture_spawn(monkeypatch)
    app = _app(tmp_path, monkeypatch, 59643)
    with _client(app) as c:
        r = c.post("/api/v1/fs/open", json={"path": str(f)})
        assert r.status_code == 204, r.text
    assert calls == [["open", str(f)]]


def test_fs_open_honours_preferred_editor(tmp_path, monkeypatch):
    """The `with` field (preferred editor) is passed to the launcher."""
    f = tmp_path / "CLAUDE.md"
    f.write_text("hi", encoding="utf-8")
    calls = _capture_spawn(monkeypatch)
    app = _app(tmp_path, monkeypatch, 59644)
    with _client(app) as c:
        r = c.post("/api/v1/fs/open", json={"path": str(f), "with": "Visual Studio Code"})
        assert r.status_code == 204, r.text
    assert calls == [["open", "-a", "Visual Studio Code", str(f)]]


def test_fs_reveal_selects_in_file_manager(tmp_path, monkeypatch):
    """POST /fs/reveal → file-manager select, 204."""
    f = tmp_path / "config.toml"
    f.write_text("", encoding="utf-8")
    calls = _capture_spawn(monkeypatch)
    app = _app(tmp_path, monkeypatch, 59645)
    with _client(app) as c:
        r = c.post("/api/v1/fs/reveal", json={"path": str(f)})
        assert r.status_code == 204, r.text
    assert calls == [["open", "-R", str(f)]]


def test_fs_open_rejects_relative_path(tmp_path, monkeypatch):
    """A non-absolute path is rejected with 400 before any spawn."""
    calls = _capture_spawn(monkeypatch)
    app = _app(tmp_path, monkeypatch, 59646)
    with _client(app) as c:
        r = c.post("/api/v1/fs/open", json={"path": "relative/notes.md"})
        assert r.status_code == 400, r.text
        assert r.json()["error"]["code"] == "FS_PATH_NOT_OPENABLE"
    assert calls == []


def test_fs_open_rejects_missing_path(tmp_path, monkeypatch):
    """An absolute path that doesn't exist is rejected with 400."""
    calls = _capture_spawn(monkeypatch)
    app = _app(tmp_path, monkeypatch, 59647)
    with _client(app) as c:
        r = c.post("/api/v1/fs/open", json={"path": str(tmp_path / "nope.md")})
        assert r.status_code == 400, r.text
        assert r.json()["error"]["code"] == "FS_PATH_NOT_OPENABLE"
    assert calls == []


def test_fs_editors_lists_detected_editors(tmp_path, monkeypatch):
    """GET /fs/editors returns the GUI editors detected on this machine."""
    monkeypatch.setattr("sys.platform", "linux")
    on_path = {"code": "/usr/bin/code", "zed": "/usr/bin/zed"}
    monkeypatch.setattr(editor_service.shutil, "which", lambda cmd: on_path.get(cmd))
    app = _app(tmp_path, monkeypatch, 59648)
    with _client(app) as c:
        r = c.get("/api/v1/fs/editors")
        assert r.status_code == 200, r.text
        editors = r.json()["editors"]
        assert {e["value"] for e in editors} == {"code", "zed"}
        assert all("label" in e and "value" in e for e in editors)


def test_fs_editors_empty_when_none_installed(tmp_path, monkeypatch):
    """No editor on PATH → an empty list (the UI falls back to system default)."""
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr(editor_service.shutil, "which", lambda cmd: None)
    app = _app(tmp_path, monkeypatch, 59649)
    with _client(app) as c:
        r = c.get("/api/v1/fs/editors")
        assert r.status_code == 200, r.text
        assert r.json()["editors"] == []


def _stub_dialog(monkeypatch, *, returncode: int, stdout: str = "") -> None:
    """Pin macOS and stub the native dialog spawn instead of opening a real one."""
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(
        pick_service.subprocess,
        "run",
        lambda cmd, **_: SimpleNamespace(returncode=returncode, stdout=stdout, stderr=""),
    )


def test_fs_pick_file_returns_chosen_path(tmp_path, monkeypatch):
    """POST /fs/pick-file → the absolute file path the user chose."""
    _stub_dialog(monkeypatch, returncode=0, stdout="/Users/me/coffer-master.key\n")
    app = _app(tmp_path, monkeypatch, 59650)
    with _client(app) as c:
        r = c.post("/api/v1/fs/pick-file", json={"start": "/Users/me"})
        assert r.status_code == 200, r.text
        assert r.json() == {"available": True, "path": "/Users/me/coffer-master.key"}


def test_fs_save_file_returns_destination_path(tmp_path, monkeypatch):
    """POST /fs/save-file → the destination path the user chose."""
    _stub_dialog(monkeypatch, returncode=0, stdout="/Users/me/out.key\n")
    app = _app(tmp_path, monkeypatch, 59651)
    with _client(app) as c:
        r = c.post("/api/v1/fs/save-file", json={"suggested_name": "out.key"})
        assert r.status_code == 200, r.text
        assert r.json() == {"available": True, "path": "/Users/me/out.key"}


def test_fs_save_file_cancel_is_available_no_path(tmp_path, monkeypatch):
    """A non-zero exit from a present dialog tool means the user cancelled."""
    _stub_dialog(monkeypatch, returncode=1, stdout="")
    app = _app(tmp_path, monkeypatch, 59652)
    with _client(app) as c:
        r = c.post("/api/v1/fs/save-file", json={})
        assert r.status_code == 200, r.text
        assert r.json() == {"available": True, "path": None}


def test_fs_pick_file_unavailable_on_host_without_dialog(tmp_path, monkeypatch):
    """No native dialog tool (Windows) → available:false so the UI falls back."""
    monkeypatch.setattr("sys.platform", "win32")
    app = _app(tmp_path, monkeypatch, 59653)
    with _client(app) as c:
        r = c.post("/api/v1/fs/pick-file", json={})
        assert r.status_code == 200, r.text
        assert r.json() == {"available": False, "path": None}
