"""Per-launcher argv for opening a command in a terminal window.

Each adapter is tested by the argument vector it builds (the launchers
themselves cannot run in CI). See spec daemon "Open an agent session in a
terminal" and "List the terminals installed on this host".
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.fs_terminal_errors import FsTerminalFailed, FsTerminalInvalid
from coffer.infrastructure.platform import terminals

CMD = "cd '/work/api' && claude --resume abc-123"
CWD = "/work/api"


def _on_path(monkeypatch: pytest.MonkeyPatch, *found: str) -> None:
    monkeypatch.setattr(
        terminals.shutil, "which", lambda c, *a, **k: f"/usr/bin/{c}" if c in found else None
    )


def test_terminal_app_runs_do_script_with_the_command_escaped_and_activates() -> None:
    launch = terminals.terminal_launch("Terminal", command='echo "a\\b"', cwd=CWD)

    assert launch.argv == [
        "osascript",
        "-e",
        'tell application "Terminal" to do script "echo \\"a\\\\b\\""',
        "-e",
        'tell application "Terminal" to activate',
    ]
    assert launch.files == ()


def test_iterm_creates_a_window_with_the_default_profile_and_writes_the_command() -> None:
    launch = terminals.terminal_launch("iTerm", command=CMD, cwd=CWD)

    assert launch.argv[0] == "osascript"
    script = "\n".join(launch.argv[2::2])
    assert "create window with default profile" in script
    assert f'write text "{CMD}"' in script
    assert "activate" in script


def test_warp_writes_a_launch_configuration_and_opens_its_uri(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    launch = terminals.terminal_launch("Warp", command=CMD, cwd=CWD)

    [(path, body)] = launch.files
    assert path.parent == tmp_path / ".warp" / "launch_configurations"
    assert path.name.startswith("coffer-") and path.suffix == ".yaml"
    assert launch.argv == ["open", f"warp://launch/{path.name}"]
    assert f'cwd: "{CWD}"' in body
    assert f'- exec: "{CMD}"' in body
    assert body.startswith("---\nname: ")


def test_orca_creates_a_focused_terminal_in_the_worktree() -> None:
    launch = terminals.terminal_launch("Orca", command=CMD, cwd=CWD)

    assert launch.argv == [
        "orca",
        "terminal",
        "create",
        "--worktree",
        f"path:{CWD}",
        "--command",
        CMD,
        "--focus",
    ]


def test_linux_launchers_run_the_command_under_a_login_shell() -> None:
    gnome = terminals.terminal_launch("gnome-terminal", command=CMD, cwd=CWD)
    konsole = terminals.terminal_launch("konsole", command=CMD, cwd=CWD)
    generic = terminals.terminal_launch("x-terminal-emulator", command=CMD, cwd=CWD)

    assert gnome.argv == ["gnome-terminal", f"--working-directory={CWD}", "--", "sh", "-lc", CMD]
    assert konsole.argv == ["konsole", "--workdir", CWD, "-e", "sh", "-lc", CMD]
    assert generic.argv == ["x-terminal-emulator", "-e", "sh", "-lc", CMD]


def test_an_unknown_launcher_is_invalid() -> None:
    with pytest.raises(FsTerminalInvalid):
        terminals.terminal_launch("hyper", command=CMD, cwd=CWD)


def test_the_system_terminal_on_macos_is_terminal_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.platform", "darwin")

    assert terminals.terminal_launch(None, command=CMD, cwd=CWD).argv[0] == "osascript"
    assert terminals.terminal_launch("  ", command=CMD, cwd=CWD).argv[0] == "osascript"


def test_the_system_terminal_on_linux_is_the_first_one_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.platform", "linux")
    _on_path(monkeypatch, "konsole", "gnome-terminal")

    assert terminals.terminal_launch(None, command=CMD, cwd=CWD).argv[0] == "gnome-terminal"
    _on_path(monkeypatch, "x-terminal-emulator", "konsole")
    assert terminals.terminal_launch(None, command=CMD, cwd=CWD).argv[0] == "x-terminal-emulator"


def test_no_terminal_on_linux_is_a_launch_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.platform", "linux")
    _on_path(monkeypatch)

    with pytest.raises(FsTerminalFailed):
        terminals.terminal_launch(None, command=CMD, cwd=CWD)


def test_macos_detection_reads_application_bundles(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "Applications" / "iTerm.app").mkdir(parents=True)
    monkeypatch.setattr(terminals, "_MAC_SYSTEM_APPS", tmp_path / "System")
    (tmp_path / "System" / "Terminal.app").mkdir(parents=True)
    _on_path(monkeypatch, "orca")

    assert terminals.terminal_launch_value(app_bundle="iTerm", command=None) == "iTerm"
    assert terminals.terminal_launch_value(app_bundle="Terminal", command=None) == "Terminal"
    assert terminals.terminal_launch_value(app_bundle="Warp", command=None) is None
    assert terminals.terminal_launch_value(app_bundle="Orca", command="orca") == "orca"


def test_linux_detection_reads_the_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.platform", "linux")
    _on_path(monkeypatch, "konsole")

    assert terminals.terminal_launch_value(app_bundle=None, command="konsole") == "konsole"
    assert terminals.terminal_launch_value(app_bundle=None, command="gnome-terminal") is None
    assert terminals.terminal_launch_value(app_bundle="Terminal", command=None) is None
