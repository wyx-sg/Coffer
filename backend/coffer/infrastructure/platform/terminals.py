"""Per-launcher argv for opening a shell command in a terminal window.

One small function per launcher, each answering with an **argument vector** (and
the files the launcher reads first) — never a shell string of the daemon's. The
command itself is a shell line the terminal's own shell runs (``cd '<dir>' &&
claude --resume <id>``); AppleScript carries it as an escaped string literal.

Also answers which of them is installed: an application bundle on macOS, a
command on ``PATH`` elsewhere — presence only, nothing is started.
"""

from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path

from coffer.application.platform_port import TerminalLaunch
from coffer.domain.fs_terminal_errors import FsTerminalFailed, FsTerminalInvalid
from coffer.infrastructure.platform.desktop import mac_app_dirs
from coffer.infrastructure.platform.host import HostOs, host_os

_MAC_SYSTEM_APPS = Path("/System/Applications/Utilities")
#: The Linux launchers tried, in order, when no terminal is chosen.
_LINUX_DEFAULTS = ("x-terminal-emulator", "gnome-terminal", "konsole")


def _applescript_str(value: str) -> str:
    esc = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{esc}"'


def _terminal_app(command: str, cwd: str) -> TerminalLaunch:
    return TerminalLaunch(
        [
            "osascript",
            "-e",
            f'tell application "Terminal" to do script {_applescript_str(command)}',
            "-e",
            'tell application "Terminal" to activate',
        ]
    )


def _iterm(command: str, cwd: str) -> TerminalLaunch:
    return TerminalLaunch(
        [
            "osascript",
            "-e",
            'tell application "iTerm"',
            "-e",
            "set w to (create window with default profile)",
            "-e",
            f"tell current session of w to write text {_applescript_str(command)}",
            "-e",
            "activate",
            "-e",
            "end tell",
        ]
    )


def _warp(command: str, cwd: str) -> TerminalLaunch:
    name = f"coffer-{uuid.uuid4().hex}"
    path = Path.home() / ".warp" / "launch_configurations" / f"{name}.yaml"
    # A JSON string is a valid YAML double-quoted scalar, so quoting is free.
    q = json.dumps
    body = (
        f"---\nname: {q(name)}\nwindows:\n  - tabs:\n      - layout:\n"
        f"          cwd: {q(cwd)}\n          commands:\n            - exec: {q(command)}\n"
    )
    return TerminalLaunch(["open", f"warp://launch/{name}.yaml"], files=((path, body),))


def _orca(command: str, cwd: str) -> TerminalLaunch:
    return TerminalLaunch(
        ["orca", "terminal", "create", "--worktree", f"path:{cwd}", "--command", command, "--focus"]
    )


def _gnome(command: str, cwd: str) -> TerminalLaunch:
    return TerminalLaunch(
        ["gnome-terminal", f"--working-directory={cwd}", "--", "sh", "-lc", command]
    )


def _konsole(command: str, cwd: str) -> TerminalLaunch:
    return TerminalLaunch(["konsole", "--workdir", cwd, "-e", "sh", "-lc", command])


def _x_terminal_emulator(command: str, cwd: str) -> TerminalLaunch:
    return TerminalLaunch(["x-terminal-emulator", "-e", "sh", "-lc", command])


_BUILDERS: dict[str, Callable[[str, str], TerminalLaunch]] = {
    "terminal": _terminal_app,
    "iterm": _iterm,
    "iterm2": _iterm,
    "warp": _warp,
    "orca": _orca,
    "gnome-terminal": _gnome,
    "konsole": _konsole,
    "x-terminal-emulator": _x_terminal_emulator,
}


def terminal_launch(launcher: str | None, *, command: str, cwd: str) -> TerminalLaunch:
    """How to run ``command`` in a new window of ``launcher`` (None: the system terminal)."""
    key = (launcher or "").strip().lower()
    if not key:
        key = _default_launcher()
    build = _BUILDERS.get(key)
    if build is None:
        raise FsTerminalInvalid(f"unknown terminal {launcher!r}")
    return build(command, cwd)


def _default_launcher() -> str:
    system = host_os()
    if system is HostOs.MACOS:
        return "terminal"
    if system is HostOs.WINDOWS:
        raise FsTerminalFailed("opening a terminal is not supported on Windows")
    for command in _LINUX_DEFAULTS:
        if shutil.which(command) is not None:
            return command
    raise FsTerminalFailed("no terminal found (x-terminal-emulator, gnome-terminal, konsole)")


def _mac_installed(app_bundle: str) -> bool:
    roots = (*mac_app_dirs(), _MAC_SYSTEM_APPS)
    return any((root / f"{app_bundle}.app").is_dir() for root in roots)


def terminal_launch_value(*, app_bundle: str | None, command: str | None) -> str | None:
    """The ``terminal`` value for an installed terminal, or None.

    macOS: the bundle name when ``<name>.app`` is in an applications directory
    (Terminal.app lives under ``/System/Applications/Utilities``), else the
    command when it is on ``PATH`` (Orca's CLI). Elsewhere: the command on ``PATH``.
    """
    if host_os() is HostOs.MACOS and app_bundle is not None and _mac_installed(app_bundle):
        return app_bundle
    if command is not None and shutil.which(command) is not None:
        return command
    return None
