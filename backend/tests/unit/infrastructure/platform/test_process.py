"""Per-OS process facts: executable names, detach flags, bundles, launchd."""

from __future__ import annotations

from coffer.infrastructure.platform import process


def test_executable_name_gets_exe_only_on_windows(monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    assert process.executable_name("coffer-daemon") == "coffer-daemon.exe"
    monkeypatch.setattr("sys.platform", "darwin")
    assert process.executable_name("coffer-daemon") == "coffer-daemon"


def test_bundles_and_launchd_are_macos_only(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    assert process.has_app_bundles() and process.has_launchd()
    monkeypatch.setattr("sys.platform", "linux")
    assert not process.has_app_bundles() and not process.has_launchd()


def test_posix_detaches_with_a_new_session(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    assert process.detached_popen_kwargs() == {"start_new_session": True}


def test_windows_detaches_without_a_console(monkeypatch):
    # The flags exist only in Windows' subprocess module; stand them in.
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr(process.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(process.subprocess, "DETACHED_PROCESS", 0x00000008, raising=False)
    assert process.detached_popen_kwargs() == {"creationflags": 0x08000008}
