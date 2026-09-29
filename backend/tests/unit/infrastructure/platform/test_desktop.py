"""Per-OS argv for the desktop file actions (spec daemon "Open and reveal
existing absolute paths", "Open the host's native folder picker").

The OS is pinned by setting ``sys.platform``; the adapter reads it per call.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.infrastructure.platform import desktop


def _file(tmp_path: pathlib.Path) -> pathlib.Path:
    f = tmp_path / "doc.md"
    f.write_text("x", encoding="utf-8")
    return f


# --- open ------------------------------------------------------------------------


def test_open_darwin_default_is_the_text_editor(tmp_path, monkeypatch):
    # Plain `open <file>` fails with kLSApplicationNotFoundErr for file types
    # with no registered default app, and the exit is swallowed → a silent no-op.
    monkeypatch.setattr("sys.platform", "darwin")
    f = _file(tmp_path)
    assert desktop.open_command(f, None) == ["open", "-t", str(f)]


def test_open_darwin_directory_goes_to_the_file_manager(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    assert desktop.open_command(tmp_path, None) == ["open", str(tmp_path)]


def test_open_darwin_with_editor(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    f = _file(tmp_path)
    assert desktop.open_command(f, "Cursor") == ["open", "-a", "Cursor", str(f)]


def test_open_blank_editor_is_treated_as_default(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    f = _file(tmp_path)
    assert desktop.open_command(f, "   ") == ["open", "-t", str(f)]


def test_open_linux_default_and_with_editor(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    f = _file(tmp_path)
    assert desktop.open_command(f, None) == ["xdg-open", str(f)]
    assert desktop.open_command(f, "code") == ["code", str(f)]


def test_open_windows_default_and_with_editor(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    f = _file(tmp_path)
    assert desktop.open_command(f, None) == ["cmd", "/c", "start", "", str(f)]
    assert desktop.open_command(f, "code") == ["code", str(f)]


# --- reveal ----------------------------------------------------------------------


def test_reveal_darwin_selects_item(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    f = _file(tmp_path)
    assert desktop.reveal_command(f) == ["open", "-R", str(f)]


def test_reveal_windows_selects_item(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    f = _file(tmp_path)
    assert desktop.reveal_command(f) == ["explorer", f"/select,{f}"]


def test_reveal_linux_degrades_to_opening_the_folder(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    assert desktop.reveal_command(_file(tmp_path)) == ["xdg-open", str(tmp_path)]
    assert desktop.reveal_command(tmp_path) == ["xdg-open", str(tmp_path)]


# --- folder picker ---------------------------------------------------------------


def test_folder_picker_darwin_uses_osascript(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    cmd = desktop.folder_picker_command("/Users/xing")
    assert cmd is not None
    assert cmd[0] == "osascript" and cmd[1] == "-e"
    assert "choose folder" in cmd[2] and 'default location (POSIX file "/Users/xing")' in cmd[2]


def test_folder_picker_darwin_escapes_the_start_into_applescript(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    cmd = desktop.folder_picker_command('/tmp/a"b\\c')
    assert cmd is not None
    assert '(POSIX file "/tmp/a\\"b\\\\c")' in cmd[2]


def test_folder_picker_darwin_without_start_has_no_default_location(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    cmd = desktop.folder_picker_command(None)
    assert cmd is not None and "default location" not in cmd[2]


def test_folder_picker_windows_is_unavailable(monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    assert desktop.folder_picker_command(None) is None


def test_folder_picker_linux_prefers_zenity(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr(
        desktop.shutil, "which", lambda t: "/usr/bin/zenity" if t == "zenity" else None
    )
    cmd = desktop.folder_picker_command("/home/x/")
    assert cmd == [
        "zenity",
        "--file-selection",
        "--directory",
        "--title=Select a folder",
        "--filename=/home/x/",
    ]


def test_folder_picker_linux_falls_back_to_kdialog(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr(
        desktop.shutil, "which", lambda t: "/usr/bin/kdialog" if t == "kdialog" else None
    )
    assert desktop.folder_picker_command(None) == ["kdialog", "--getexistingdirectory", ""]


def test_folder_picker_linux_none_available(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr(desktop.shutil, "which", lambda _t: None)
    assert desktop.folder_picker_command(None) is None


# --- editor detection ------------------------------------------------------------


def test_editor_on_macos_is_found_by_bundle_name(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(desktop, "mac_app_installed", lambda name: name == "Zed")
    assert desktop.editor_launch_value(app_bundle="Zed", command="zed") == "Zed"
    assert desktop.editor_launch_value(app_bundle="Cursor", command="cursor") is None
    # A command-only editor does not exist on macOS.
    assert desktop.editor_launch_value(app_bundle=None, command="gedit") is None


def test_mac_app_installed_looks_in_the_applications_dirs(tmp_path, monkeypatch):
    (tmp_path / "Zed.app").mkdir()
    monkeypatch.setattr(desktop, "mac_app_dirs", lambda: (tmp_path,))
    assert desktop.mac_app_installed("Zed") is True
    assert desktop.mac_app_installed("Nova") is False


@pytest.mark.parametrize("host", ["linux", "win32"])
def test_editor_elsewhere_is_found_on_path(monkeypatch, host):
    monkeypatch.setattr("sys.platform", host)
    monkeypatch.setattr(desktop.shutil, "which", lambda c: "/bin/code" if c == "code" else None)
    assert desktop.editor_launch_value(app_bundle="Visual Studio Code", command="code") == "code"
    assert desktop.editor_launch_value(app_bundle="Zed", command="zed") is None
    # A GUI-only (bundle-only) editor is never offered off macOS.
    assert desktop.editor_launch_value(app_bundle="Nova", command=None) is None
