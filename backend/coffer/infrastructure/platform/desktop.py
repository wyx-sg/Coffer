"""Per-OS argv for the desktop file actions: open, reveal, pick a folder, find an editor.

Moved here from ``application/fs`` so the use cases there (validation, spawn,
result mapping) no longer branch on the OS. Every function builds an
**argument vector** — never a shell string — and runs nothing except the
``PATH`` / application-bundle probes that decide which tool is present.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from coffer.infrastructure.platform.host import HostOs, host_os


def open_command(target: Path, with_app: str | None) -> list[str]:
    """The argv that opens ``target`` in ``with_app`` (an app name/path) or the default."""
    s = str(target)
    app = (with_app or "").strip()
    system = host_os()
    if system is HostOs.MACOS:
        if app:
            return ["open", "-a", app, s]
        # A directory goes to the Finder: `-t` would hand the folder to the
        # default text editor, which refuses it ("cannot open files in the
        # folder format").
        if target.is_dir():
            return ["open", s]
        # No editor chosen → `open -t` opens the default *text* editor. Plain
        # `open <file>` fails (kLSApplicationNotFoundErr) for file types with no
        # registered default app — common for the extensionless config files
        # Coffer manages — and the non-zero exit is swallowed, so nothing opens.
        return ["open", "-t", s]
    if system is HostOs.WINDOWS:
        # `start` needs an empty title arg; an explicit app is launched directly.
        return [app, s] if app else ["cmd", "/c", "start", "", s]
    # Linux / other: a chosen editor is launched directly; otherwise xdg-open.
    return [app, s] if app else ["xdg-open", s]


def reveal_command(target: Path) -> list[str]:
    """The argv that selects ``target`` in the OS file manager."""
    s = str(target)
    system = host_os()
    if system is HostOs.MACOS:
        return ["open", "-R", s]
    if system is HostOs.WINDOWS:
        return ["explorer", f"/select,{s}"]
    # Linux has no portable "select the file" — degrade to opening the folder.
    folder = target if target.is_dir() else target.parent
    return ["xdg-open", str(folder)]


def _applescript_str(value: str) -> str:
    """Quote a Python string as an AppleScript string literal (escaped)."""
    esc = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{esc}"'


def _applescript_posix_file(path: str) -> str:
    """An AppleScript ``POSIX file`` reference for use as a default location."""
    return f"(POSIX file {_applescript_str(path)})"


def folder_picker_command(start: str | None) -> list[str] | None:
    """The native folder-dialog argv for this host, or None if none is available.

    On macOS the start folder is escaped into an AppleScript string literal.
    """
    system = host_os()
    if system is HostOs.MACOS:
        location = f" default location {_applescript_posix_file(start)}" if start else ""
        script = f'POSIX path of (choose folder with prompt "Select a folder"{location})'
        return ["osascript", "-e", script]
    if system is HostOs.WINDOWS:
        # No simple argv-only native dialog; caller falls back to the in-app browser.
        return None
    # Linux / other: prefer zenity, then kdialog.
    if shutil.which("zenity"):
        cmd = ["zenity", "--file-selection", "--directory", "--title=Select a folder"]
        if start:
            cmd.append(f"--filename={start.rstrip('/')}/")
        return cmd
    if shutil.which("kdialog"):
        return ["kdialog", "--getexistingdirectory", start or ""]
    return None


def mac_app_dirs() -> tuple[Path, ...]:
    """The standard macOS applications directories."""
    return (Path("/Applications"), Path.home() / "Applications")


def mac_app_installed(app_name: str) -> bool:
    """True if ``<app_name>.app`` exists in a standard macOS applications dir."""
    return any((root / f"{app_name}.app").is_dir() for root in mac_app_dirs())


def editor_launch_value(*, app_bundle: str | None, command: str | None) -> str | None:
    """The value :func:`open_command` accepts as ``with_app`` for an installed editor.

    * **macOS** — ``open -a <app>`` wants an application *name*: the bundle
      name, when ``<name>.app`` is under ``/Applications`` or ``~/Applications``.
    * **Linux / Windows** — the launcher runs the value as an executable: the
      command, when :func:`shutil.which` finds it on ``PATH``.
    """
    if host_os() is HostOs.MACOS:
        if app_bundle is not None and mac_app_installed(app_bundle):
            return app_bundle
        return None
    if command is not None and shutil.which(command) is not None:
        return command
    return None
