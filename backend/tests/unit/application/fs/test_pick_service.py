"""Unit coverage for FsPickService — the native folder dialog (spec daemon
"Open the host's native folder picker")."""

from __future__ import annotations

from types import SimpleNamespace

from coffer.application.fs import pick_service
from coffer.application.fs.pick_service import (
    FsPickService,
    _folder_cmd,
    _usable_start,
)


def _run(returncode: int, stdout: str = ""):
    return lambda cmd, **_: SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")


# --- _folder_cmd: per-platform argv -------------------------------------------


def test_folder_cmd_darwin_uses_osascript(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "darwin")
    cmd = _folder_cmd("/Users/xing")
    assert cmd is not None
    assert cmd[0] == "osascript" and cmd[1] == "-e"
    assert "choose folder" in cmd[2] and "/Users/xing" in cmd[2]


def test_folder_cmd_windows_is_unavailable(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "win32")
    assert _folder_cmd(None) is None


def test_folder_cmd_linux_prefers_zenity(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "linux")
    monkeypatch.setattr(
        pick_service.shutil, "which", lambda t: "/usr/bin/zenity" if t == "zenity" else None
    )
    cmd = _folder_cmd(None)
    assert cmd is not None and cmd[0] == "zenity" and "--directory" in cmd


def test_folder_cmd_linux_none_available(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "linux")
    monkeypatch.setattr(pick_service.shutil, "which", lambda _t: None)
    assert _folder_cmd(None) is None


# --- pick_folder: outcomes ----------------------------------------------------


def test_pick_folder_returns_selected_path(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "darwin")
    monkeypatch.setattr(pick_service.subprocess, "run", _run(0, "/Users/xing/wedding-invitation\n"))
    result = FsPickService().pick_folder("/Users/xing")
    assert result.available is True
    assert result.path == "/Users/xing/wedding-invitation"


def test_pick_cancel_is_available_no_path(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "darwin")
    monkeypatch.setattr(pick_service.subprocess, "run", _run(1, ""))
    assert FsPickService().pick_folder(None) == pick_service.PickResult(available=True, path=None)


def test_pick_folder_unavailable_when_no_tool(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "linux")
    monkeypatch.setattr(pick_service.shutil, "which", lambda _t: None)
    result = FsPickService().pick_folder(None)
    assert result.available is False and result.path is None


def test_pick_folder_unavailable_when_spawn_errors(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "darwin")

    def _boom(cmd, **_):
        raise OSError("gone")

    monkeypatch.setattr(pick_service.subprocess, "run", _boom)
    result = FsPickService().pick_folder(None)
    assert result.available is False and result.path is None


# --- the start folder ---------------------------------------------------------


def test_usable_start_keeps_an_existing_directory(monkeypatch):
    monkeypatch.setattr(pick_service.os.path, "isdir", lambda p: p == "/Users/xing/skills")
    assert _usable_start(" /Users/xing/skills ") == "/Users/xing/skills"


def test_usable_start_drops_a_half_typed_path(monkeypatch):
    monkeypatch.setattr(pick_service.os.path, "isdir", lambda _p: False)
    assert _usable_start("/Users/xing/ski") is None
    assert _usable_start("   ") is None
    assert _usable_start(None) is None


def test_pick_folder_opens_without_a_start_it_cannot_use(monkeypatch):
    # macOS exits non-zero, without a dialog, on a default location that does not
    # exist; that must not be passed, or Browse would read as a silent cancel.
    monkeypatch.setattr(pick_service.sys, "platform", "darwin")
    monkeypatch.setattr(pick_service.os.path, "isdir", lambda _p: False)
    seen: list[list[str]] = []

    def run(cmd, **_):
        seen.append(cmd)
        return SimpleNamespace(returncode=0, stdout="/Users/xing/skills\n", stderr="")

    monkeypatch.setattr(pick_service.subprocess, "run", run)
    assert FsPickService().pick_folder("/Users/xing/ski").path == "/Users/xing/skills"
    assert "default location" not in seen[0][2]
