"""Unit coverage for EditorDetectService (preferred-editor picker detection)."""

from __future__ import annotations

from coffer.application.fs import editor_service
from coffer.application.fs.editor_service import EditorDetectService


def test_lists_macos_apps_by_bundle_name(monkeypatch):
    """On macOS, installed .app bundles are returned by their app name."""
    monkeypatch.setattr("sys.platform", "darwin")
    installed = {"Visual Studio Code", "Zed"}
    monkeypatch.setattr(editor_service, "_mac_app_installed", lambda name: name in installed)

    options = EditorDetectService().list_editors()

    values = [o.value for o in options]
    assert values == ["Visual Studio Code", "Zed"]  # curated order preserved
    vscode = next(o for o in options if o.value == "Visual Studio Code")
    assert vscode.label == "Visual Studio Code"


def test_lists_path_executables_on_linux(monkeypatch):
    """On Linux, editors resolvable on PATH are returned by their command."""
    monkeypatch.setattr("sys.platform", "linux")
    on_path = {"code": "/usr/bin/code", "subl": "/usr/bin/subl"}
    monkeypatch.setattr(editor_service.shutil, "which", lambda cmd: on_path.get(cmd))

    options = EditorDetectService().list_editors()

    assert [o.value for o in options] == ["code", "subl"]


def test_returns_empty_when_nothing_installed(monkeypatch):
    """No installed editor → empty list (the UI falls back to system default)."""
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr(editor_service.shutil, "which", lambda cmd: None)

    assert EditorDetectService().list_editors() == []


def test_gui_only_editors_are_skipped_on_linux(monkeypatch):
    """A macOS-only editor (no command) is never returned on Linux even if a
    same-named binary somehow resolves — detection keys off the command field."""
    monkeypatch.setattr("sys.platform", "linux")
    # `which` says everything is present; Nova/Xcode/Emacs have command=None so
    # they must still be excluded on Linux.
    monkeypatch.setattr(editor_service.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")

    values = {o.value for o in EditorDetectService().list_editors()}
    assert "Nova" not in values
    assert "Xcode" not in values
