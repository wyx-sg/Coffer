"""Unit coverage for FsPickService — native folder dialog (FR-024, ADR-033)."""

from __future__ import annotations

from types import SimpleNamespace

from coffer.application.fs import pick_service
from coffer.application.fs.pick_service import FsPickService, _pick_cmd


def _run(returncode: int, stdout: str = ""):
    return lambda cmd, **_: SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")


# --- _pick_cmd: per-platform argv ---------------------------------------------


def test_pick_cmd_darwin_uses_osascript(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "darwin")
    cmd = _pick_cmd("/Users/xing")
    assert cmd is not None
    assert cmd[0] == "osascript" and cmd[1] == "-e"
    assert "choose folder" in cmd[2] and "/Users/xing" in cmd[2]


def test_pick_cmd_windows_is_unavailable(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "win32")
    assert _pick_cmd(None) is None


def test_pick_cmd_linux_prefers_zenity(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "linux")
    monkeypatch.setattr(
        pick_service.shutil, "which", lambda t: "/usr/bin/zenity" if t == "zenity" else None
    )
    cmd = _pick_cmd(None)
    assert cmd is not None and cmd[0] == "zenity" and "--directory" in cmd


def test_pick_cmd_linux_none_available(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "linux")
    monkeypatch.setattr(pick_service.shutil, "which", lambda _t: None)
    assert _pick_cmd(None) is None


# --- pick_folder: outcomes ----------------------------------------------------


def test_pick_folder_returns_selected_path(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "darwin")
    monkeypatch.setattr(pick_service.subprocess, "run", _run(0, "/Users/xing/wedding-invitation\n"))
    result = FsPickService().pick_folder("/Users/xing")
    assert result.available is True
    assert result.path == "/Users/xing/wedding-invitation"


def test_pick_folder_cancel_is_available_no_path(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "darwin")
    monkeypatch.setattr(pick_service.subprocess, "run", _run(1, ""))
    result = FsPickService().pick_folder(None)
    assert result.available is True and result.path is None


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
