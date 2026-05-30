"""Unit tests for daemon_spawn_command() — ADR-006 frozen-aware spawn.

TEST-019: daemon_spawn_command() returns the correct launch command in both
dev/pip mode (not frozen) and PyInstaller frozen mode.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from coffer.infrastructure.daemon.spawn import daemon_spawn_command

# --------------------------------------------------------------------------- #
# Not-frozen path                                                               #
# --------------------------------------------------------------------------- #


def test_not_frozen_returns_python_module_invocation(monkeypatch: pytest.MonkeyPatch) -> None:
    """In dev/pip mode (no sys.frozen), the command must be
    [sys.executable, '-m', 'coffer.infrastructure.daemon.entry']."""
    # Ensure not frozen — remove the attribute if it was set (e.g. by PyInstaller).
    monkeypatch.delattr(sys, "frozen", raising=False)

    cmd = daemon_spawn_command()

    assert cmd == [sys.executable, "-m", "coffer.infrastructure.daemon.entry"]


def test_not_frozen_uses_current_sys_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    """The command's first element matches sys.executable."""
    monkeypatch.delattr(sys, "frozen", raising=False)

    cmd = daemon_spawn_command()

    assert cmd[0] == sys.executable


# --------------------------------------------------------------------------- #
# Frozen path — POSIX                                                           #
# --------------------------------------------------------------------------- #


def test_frozen_posix_returns_coffer_daemon_sibling(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When sys.frozen=True on POSIX and nothing on PATH, fall back to the
    'coffer-daemon' path next to sys.executable (best effort)."""
    fake_exe = tmp_path / "coffer"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.setattr(sys, "platform", "linux")
    # Deterministic regardless of the test host's PATH.
    monkeypatch.setattr("coffer.infrastructure.daemon.spawn.shutil.which", lambda _n: None)

    cmd = daemon_spawn_command()

    expected = str((tmp_path / "coffer-daemon").resolve())
    assert cmd == [expected]


def test_frozen_prefers_existing_sibling_over_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When the co-located sibling exists (CLI-tarball layout), it wins — even
    if a different coffer-daemon is also on PATH."""
    fake_exe = tmp_path / "coffer"
    sibling = tmp_path / "coffer-daemon"
    sibling.write_text("#!/bin/sh\n")  # make it exist
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        "coffer.infrastructure.daemon.spawn.shutil.which",
        lambda _n: "/usr/bin/coffer-daemon",
    )

    cmd = daemon_spawn_command()

    assert cmd == [str(sibling.resolve())]


def test_frozen_falls_back_to_path_when_no_sibling(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When the sibling is absent (e.g. a desktop-deployed shim) but
    coffer-daemon is on PATH, use the PATH location so spawn still works."""
    fake_exe = tmp_path / "coffer-mcp-shim"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        "coffer.infrastructure.daemon.spawn.shutil.which",
        lambda _n: "/opt/coffer/coffer-daemon",
    )

    cmd = daemon_spawn_command()

    assert cmd == ["/opt/coffer/coffer-daemon"]


# --------------------------------------------------------------------------- #
# Frozen path — Windows                                                         #
# --------------------------------------------------------------------------- #


def test_frozen_windows_returns_coffer_daemon_exe_sibling(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When sys.frozen=True on Windows (sys.platform == 'win32'), the binary
    name must have the .exe suffix."""
    fake_exe = tmp_path / "coffer.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr("coffer.infrastructure.daemon.spawn.shutil.which", lambda _n: None)

    cmd = daemon_spawn_command()

    expected = str((tmp_path / "coffer-daemon.exe").resolve())
    assert cmd == [expected]
