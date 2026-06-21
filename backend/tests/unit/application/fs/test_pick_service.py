"""Unit coverage for FsPickService — native folder/file/save dialogs (FR-042, ADR-036)."""

from __future__ import annotations

from types import SimpleNamespace

from coffer.application.fs import pick_service
from coffer.application.fs.pick_service import (
    FsPickService,
    _file_cmd,
    _folder_cmd,
    _save_cmd,
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


# --- _file_cmd: per-platform argv ---------------------------------------------


def test_file_cmd_darwin_uses_choose_file(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "darwin")
    cmd = _file_cmd("/Users/xing")
    assert cmd is not None
    assert cmd[0] == "osascript" and cmd[1] == "-e"
    assert "choose file" in cmd[2] and "choose file name" not in cmd[2]
    assert "/Users/xing" in cmd[2]


def test_file_cmd_windows_is_unavailable(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "win32")
    assert _file_cmd(None) is None


def test_file_cmd_linux_prefers_zenity(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "linux")
    monkeypatch.setattr(
        pick_service.shutil, "which", lambda t: "/usr/bin/zenity" if t == "zenity" else None
    )
    cmd = _file_cmd(None)
    assert cmd is not None and cmd[0] == "zenity" and "--directory" not in cmd


def test_file_cmd_zenity_seeds_start_dir_with_trailing_slash(monkeypatch):
    # A bare start dir must get a trailing slash so GTK opens inside it rather
    # than pre-selecting its last component as a file name.
    monkeypatch.setattr(pick_service.sys, "platform", "linux")
    monkeypatch.setattr(
        pick_service.shutil, "which", lambda t: "/usr/bin/zenity" if t == "zenity" else None
    )
    assert "--filename=/home/u/" in _file_cmd("/home/u")


def test_file_cmd_linux_kdialog_fallback(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "linux")
    monkeypatch.setattr(
        pick_service.shutil, "which", lambda t: "/usr/bin/kdialog" if t == "kdialog" else None
    )
    cmd = _file_cmd(None)
    assert cmd is not None and cmd[0] == "kdialog" and "--getopenfilename" in cmd


# --- _save_cmd: per-platform argv ---------------------------------------------


def test_save_cmd_darwin_uses_choose_file_name(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "darwin")
    cmd = _save_cmd("coffer-master.key", "/Users/xing")
    assert cmd is not None
    assert cmd[0] == "osascript" and cmd[1] == "-e"
    assert "choose file name" in cmd[2]
    assert "coffer-master.key" in cmd[2] and "/Users/xing" in cmd[2]


def test_save_cmd_windows_is_unavailable(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "win32")
    assert _save_cmd("x.key", None) is None


def test_save_cmd_linux_zenity_seeds_filename(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "linux")
    monkeypatch.setattr(
        pick_service.shutil, "which", lambda t: "/usr/bin/zenity" if t == "zenity" else None
    )
    cmd = _save_cmd("x.key", "/home/u")
    assert cmd is not None and cmd[0] == "zenity"
    assert "--save" in cmd and "--confirm-overwrite" in cmd
    assert "--filename=/home/u/x.key" in cmd


def test_save_cmd_linux_none_available(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "linux")
    monkeypatch.setattr(pick_service.shutil, "which", lambda _t: None)
    assert _save_cmd("x.key", None) is None


# --- pick_folder / pick_file / save_file: outcomes ----------------------------


def test_pick_folder_returns_selected_path(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "darwin")
    monkeypatch.setattr(pick_service.subprocess, "run", _run(0, "/Users/xing/wedding-invitation\n"))
    result = FsPickService().pick_folder("/Users/xing")
    assert result.available is True
    assert result.path == "/Users/xing/wedding-invitation"


def test_pick_file_returns_selected_path(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "darwin")
    monkeypatch.setattr(pick_service.subprocess, "run", _run(0, "/Users/xing/coffer-master.key\n"))
    result = FsPickService().pick_file("/Users/xing")
    assert result.available is True
    assert result.path == "/Users/xing/coffer-master.key"


def test_save_file_returns_destination_path(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "darwin")
    monkeypatch.setattr(pick_service.subprocess, "run", _run(0, "/Users/xing/out.key\n"))
    result = FsPickService().save_file("out.key", "/Users/xing")
    assert result.available is True
    assert result.path == "/Users/xing/out.key"


def test_pick_cancel_is_available_no_path(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "darwin")
    monkeypatch.setattr(pick_service.subprocess, "run", _run(1, ""))
    assert FsPickService().pick_file(None) == pick_service.PickResult(available=True, path=None)
    assert FsPickService().save_file(None, None) == pick_service.PickResult(
        available=True, path=None
    )


def test_pick_file_unavailable_when_no_tool(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "linux")
    monkeypatch.setattr(pick_service.shutil, "which", lambda _t: None)
    result = FsPickService().pick_file(None)
    assert result.available is False and result.path is None


def test_save_file_unavailable_when_spawn_errors(monkeypatch):
    monkeypatch.setattr(pick_service.sys, "platform", "darwin")

    def _boom(cmd, **_):
        raise OSError("gone")

    monkeypatch.setattr(pick_service.subprocess, "run", _boom)
    result = FsPickService().save_file("x.key", None)
    assert result.available is False and result.path is None
