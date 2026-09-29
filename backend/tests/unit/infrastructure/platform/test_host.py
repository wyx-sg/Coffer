"""Host identification and the ``HostPlatform`` adapter."""

from __future__ import annotations

import pathlib

import pytest

from coffer.application.platform_port import PlatformPort
from coffer.infrastructure.platform import HostOs, HostPlatform, host_os
from coffer.infrastructure.platform import host as host_mod


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("darwin", HostOs.MACOS),
        ("win32", HostOs.WINDOWS),
        ("linux", HostOs.LINUX),
        ("freebsd14", HostOs.OTHER),
    ],
)
def test_host_os_follows_sys_platform(monkeypatch, value, expected):
    monkeypatch.setattr("sys.platform", value)
    assert host_os() is expected


def test_os_label_is_system_and_release(monkeypatch):
    monkeypatch.setattr(host_mod.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(host_mod.platform, "release", lambda: "24.6.0")
    assert host_mod.os_label() == "Darwin 24.6.0"


def test_os_label_strips_an_empty_release(monkeypatch):
    monkeypatch.setattr(host_mod.platform, "system", lambda: "Linux")
    monkeypatch.setattr(host_mod.platform, "release", lambda: "")
    assert host_mod.os_label() == "Linux"


def test_host_platform_answers_through_the_port(tmp_path: pathlib.Path, monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    port: PlatformPort = HostPlatform()
    f = tmp_path / "a.md"
    f.write_text("x", encoding="utf-8")
    assert port.open_command(f, None) == ["open", "-t", str(f)]
    assert port.reveal_command(f) == ["open", "-R", str(f)]
    assert port.privileged_paths().firmlink_root == "/private"
    picker = port.folder_picker_command(None)
    assert picker is not None and picker[0] == "osascript"
    assert isinstance(port.os_label(), str)
    assert port.editor_launch_value(app_bundle=None, command="gedit") is None
