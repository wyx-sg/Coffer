"""Unit coverage for FsPickService — the native folder dialog (spec daemon
"Open the host's native folder picker").

The per-OS dialog argv is the platform adapter's answer
(``tests/unit/infrastructure/platform/test_desktop.py``); here the port is a
fake, so these tests cover the three-outcome contract and the start folder.
"""

from __future__ import annotations

from types import SimpleNamespace

from coffer.application.fs import pick_service
from coffer.application.fs.pick_service import FsPickService, _usable_start

from ._fake_platform import FakePlatform


def _run(returncode: int, stdout: str = ""):
    return lambda cmd, **_: SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")


# --- pick_folder: outcomes ----------------------------------------------------


def test_pick_folder_returns_selected_path(monkeypatch):
    monkeypatch.setattr(pick_service.subprocess, "run", _run(0, "/Users/xing/wedding-invitation\n"))
    result = FsPickService(FakePlatform()).pick_folder("/Users/xing")
    assert result.available is True
    assert result.path == "/Users/xing/wedding-invitation"


def test_pick_cancel_is_available_no_path(monkeypatch):
    monkeypatch.setattr(pick_service.subprocess, "run", _run(1, ""))
    result = FsPickService(FakePlatform()).pick_folder(None)
    assert result == pick_service.PickResult(available=True, path=None)


def test_pick_folder_unavailable_when_no_tool():
    result = FsPickService(FakePlatform(picker=None)).pick_folder(None)
    assert result.available is False and result.path is None


def test_pick_folder_unavailable_when_spawn_errors(monkeypatch):
    def _boom(cmd, **_):
        raise OSError("gone")

    monkeypatch.setattr(pick_service.subprocess, "run", _boom)
    result = FsPickService(FakePlatform()).pick_folder(None)
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
    monkeypatch.setattr(pick_service.os.path, "isdir", lambda _p: False)
    monkeypatch.setattr(pick_service.subprocess, "run", _run(0, "/Users/xing/skills\n"))
    platform = FakePlatform()
    assert FsPickService(platform).pick_folder("/Users/xing/ski").path == "/Users/xing/skills"
    assert platform.picker_starts == [None]
