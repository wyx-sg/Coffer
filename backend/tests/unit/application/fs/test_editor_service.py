"""Unit coverage for EditorDetectService (preferred-editor picker detection).

Whether an editor is installed, and which value launches it, is the platform
adapter's answer (``tests/unit/infrastructure/platform/test_desktop.py``);
here the port is a fake.
"""

from __future__ import annotations

from coffer.application.fs.editor_service import EditorDetectService

from ._fake_platform import FakePlatform


def test_lists_what_the_platform_reports_installed_in_curated_order():
    platform = FakePlatform(editors={"Zed": "Zed", "Visual Studio Code": "Visual Studio Code"})

    options = EditorDetectService(platform).list_editors()

    assert [o.value for o in options] == ["Visual Studio Code", "Zed"]
    assert options[0].label == "Visual Studio Code"


def test_the_launch_value_is_the_platforms_not_the_label():
    # Kate has no application bundle, so the port is asked by its command.
    platform = FakePlatform(editors={"kate": "/usr/bin/kate-launcher"})

    options = EditorDetectService(platform).list_editors()

    assert [(o.label, o.value) for o in options] == [("Kate", "/usr/bin/kate-launcher")]


def test_returns_empty_when_nothing_installed():
    """No installed editor → empty list (the UI falls back to system default)."""
    assert EditorDetectService(FakePlatform()).list_editors() == []
