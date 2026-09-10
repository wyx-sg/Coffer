"""Native OS picker dialogs via the loopback daemon (spec 004 FR-042).

A web browser cannot open an OS-native file/folder dialog that returns an
absolute path. But the daemon is *always co-located with the client on the
user's own machine*, so it can invoke the host's native dialog (``osascript`` on
macOS, ``zenity``/``kdialog`` on Linux) and hand back the chosen path. Three
dialogs share one mechanism: pick a folder, pick an existing file, or choose a
save destination.

Every dialog returns the same three outcomes so the caller can react correctly:
  * ``available=False``           — no native dialog tool on this host. The
    caller falls back to the in-app folder browser (folder picking) or to a
    typed path (file/save picking).
  * ``available=True, path=None`` — the dialog opened and the user cancelled.
  * ``available=True, path="…"``  — the user chose an absolute path.

Safety: the picker is invoked with an **argument vector** (never a shell string);
on macOS the start dir and suggested name are escaped into AppleScript string
literals.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class PickResult:
    available: bool
    path: str | None


class FsPickService:
    """Open the host's native folder dialog and return the chosen path.

    Only *folders*. The open- and save-file dialogs this used to offer are gone:
    a browser has `<input type="file">` and `<a download>` for those, and they
    hand over file contents rather than a path, which is what a web page can
    actually use. A folder is the exception the browser has no answer for — it
    deliberately withholds absolute paths, and registering an agent needs one.
    """

    def pick_folder(self, start: str | None = None) -> PickResult:
        return _run_dialog(_folder_cmd(start))


def _run_dialog(cmd: list[str] | None) -> PickResult:
    """Run a native-dialog argv and map its result to the three-outcome contract."""
    if cmd is None:
        return PickResult(available=False, path=None)
    try:
        # Blocking: a modal dialog returns only when the user picks/cancels.
        # The HTTP layer runs this in a worker thread (asyncio.to_thread).
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError:
        # The tool vanished between the which() probe and the spawn.
        return PickResult(available=False, path=None)
    if proc.returncode == 0:
        picked = proc.stdout.strip()
        return PickResult(available=True, path=picked or None)
    # A non-zero exit from a present dialog tool means the user cancelled.
    return PickResult(available=True, path=None)


def _applescript_str(value: str) -> str:
    """Quote a Python string as an AppleScript string literal (escaped)."""
    esc = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{esc}"'


def _applescript_posix_file(path: str) -> str:
    """An AppleScript ``POSIX file`` reference for use as a default location."""
    return f"(POSIX file {_applescript_str(path)})"


def _folder_cmd(start: str | None) -> list[str] | None:
    """The native folder-dialog argv for this host, or None if none is available."""
    if sys.platform == "darwin":
        location = f" default location {_applescript_posix_file(start)}" if start else ""
        script = f'POSIX path of (choose folder with prompt "Select a folder"{location})'
        return ["osascript", "-e", script]
    if sys.platform == "win32":
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
