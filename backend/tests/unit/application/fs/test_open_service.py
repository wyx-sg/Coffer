"""Unit coverage for FsOpenService command building + validation (FR-039, ADR-033)."""

from __future__ import annotations

import pathlib

import pytest

from coffer.application.fs import open_service
from coffer.application.fs.open_service import FsOpenService
from coffer.domain.errors import FsPathNotOpenable


@pytest.fixture
def captured(monkeypatch) -> list[list[str]]:
    calls: list[list[str]] = []
    monkeypatch.setattr(open_service.subprocess, "Popen", lambda cmd, **_: calls.append(cmd))
    return calls


def _file(tmp_path: pathlib.Path) -> str:
    f = tmp_path / "doc.md"
    f.write_text("x", encoding="utf-8")
    return str(f)


# --- open: per-platform argv ---------------------------------------------------


def test_open_darwin_default(tmp_path, monkeypatch, captured):
    # System default → open in the default TEXT editor (`open -t`). Plain
    # `open <file>` fails with kLSApplicationNotFoundErr for file types that
    # have no registered default app (extensionless config files etc.), and the
    # non-zero exit is swallowed → a silent no-op. `-t` always resolves to the
    # default text editor (TextEdit at worst), which is what "open in editor" means.
    monkeypatch.setattr("sys.platform", "darwin")
    path = _file(tmp_path)
    FsOpenService().open(path)
    assert captured == [["open", "-t", path]]


def test_open_darwin_with_editor(tmp_path, monkeypatch, captured):
    monkeypatch.setattr("sys.platform", "darwin")
    path = _file(tmp_path)
    FsOpenService().open(path, with_app="Cursor")
    assert captured == [["open", "-a", "Cursor", path]]


def test_open_linux_default(tmp_path, monkeypatch, captured):
    monkeypatch.setattr("sys.platform", "linux")
    path = _file(tmp_path)
    FsOpenService().open(path)
    assert captured == [["xdg-open", path]]


def test_open_linux_with_editor_launches_it_directly(tmp_path, monkeypatch, captured):
    monkeypatch.setattr("sys.platform", "linux")
    path = _file(tmp_path)
    FsOpenService().open(path, with_app="code")
    assert captured == [["code", path]]


def test_open_windows_default(tmp_path, monkeypatch, captured):
    monkeypatch.setattr("sys.platform", "win32")
    path = _file(tmp_path)
    FsOpenService().open(path)
    assert captured == [["cmd", "/c", "start", "", path]]


def test_open_blank_editor_is_treated_as_default(tmp_path, monkeypatch, captured):
    monkeypatch.setattr("sys.platform", "darwin")
    path = _file(tmp_path)
    FsOpenService().open(path, with_app="   ")
    assert captured == [["open", "-t", path]]


# --- reveal: per-platform argv -------------------------------------------------


def test_reveal_darwin_selects_item(tmp_path, monkeypatch, captured):
    monkeypatch.setattr("sys.platform", "darwin")
    path = _file(tmp_path)
    FsOpenService().reveal(path)
    assert captured == [["open", "-R", path]]


def test_reveal_windows_selects_item(tmp_path, monkeypatch, captured):
    monkeypatch.setattr("sys.platform", "win32")
    path = _file(tmp_path)
    FsOpenService().reveal(path)
    assert captured == [["explorer", f"/select,{path}"]]


def test_reveal_linux_degrades_to_opening_the_folder(tmp_path, monkeypatch, captured):
    monkeypatch.setattr("sys.platform", "linux")
    path = _file(tmp_path)
    FsOpenService().reveal(path)
    # No portable "select the file" on Linux — opens the containing folder.
    assert captured == [["xdg-open", str(tmp_path)]]


def test_reveal_linux_directory_opens_itself(tmp_path, monkeypatch, captured):
    monkeypatch.setattr("sys.platform", "linux")
    FsOpenService().reveal(str(tmp_path))
    assert captured == [["xdg-open", str(tmp_path)]]


# --- validation: nothing is spawned for a bad path -----------------------------


def test_open_rejects_relative_path(tmp_path, captured):
    with pytest.raises(FsPathNotOpenable) as exc:
        FsOpenService().open("relative/doc.md")
    assert exc.value.reason == "not_absolute"
    assert captured == []


def test_open_rejects_empty_path(captured):
    with pytest.raises(FsPathNotOpenable):
        FsOpenService().open("")
    assert captured == []


def test_open_rejects_missing_path(tmp_path, captured):
    with pytest.raises(FsPathNotOpenable) as exc:
        FsOpenService().open(str(tmp_path / "nope.md"))
    assert exc.value.reason == "not_found"
    assert captured == []


def test_reveal_rejects_missing_path(tmp_path, captured):
    with pytest.raises(FsPathNotOpenable):
        FsOpenService().reveal(str(tmp_path / "gone"))
    assert captured == []


def test_launch_failure_becomes_fs_path_not_openable(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    path = _file(tmp_path)

    def boom(cmd, **_):
        raise OSError("no launcher")

    monkeypatch.setattr(open_service.subprocess, "Popen", boom)
    with pytest.raises(FsPathNotOpenable) as exc:
        FsOpenService().open(path)
    assert exc.value.reason == "launch_failed"


def test_spawn_detaches_and_silences_output(tmp_path, monkeypatch):
    """The launcher is detached (start_new_session) with stdout/stderr discarded,
    so a long-lived editor never holds the daemon nor leaks into its streams."""
    monkeypatch.setattr("sys.platform", "darwin")
    path = _file(tmp_path)
    seen: dict[str, object] = {}
    monkeypatch.setattr(open_service.subprocess, "Popen", lambda cmd, **kw: seen.update(kw))
    FsOpenService().open(path)
    assert seen["start_new_session"] is True
    assert seen["stdout"] == open_service.subprocess.DEVNULL
    assert seen["stderr"] == open_service.subprocess.DEVNULL
