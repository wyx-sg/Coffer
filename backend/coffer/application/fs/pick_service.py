"""Native OS folder-picker via the loopback daemon (spec 004 FR-024, ADR-033).

A web browser cannot open an OS-native directory dialog that returns an absolute
path, which is why the web folder picker falls back to an in-app browser
(:class:`FsBrowseService`). But the daemon is *always co-located with the client
on the user's own machine*, so it can invoke the host's native dialog
(``osascript`` on macOS, ``zenity``/``kdialog`` on Linux) and hand back the
chosen path.

The result distinguishes three outcomes so the caller can react correctly:
  * ``available=False``           — no native dialog tool on this host → the
    caller should fall back to the in-app folder browser.
  * ``available=True, path=None`` — the dialog opened and the user cancelled.
  * ``available=True, path="…"``  — the user picked an absolute directory path.

Safety: the picker is invoked with an **argument vector** (never a shell string);
on macOS the start dir is escaped into the AppleScript string literal.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class FolderPickResult:
    available: bool
    path: str | None


class FsPickService:
    """Open the host's native folder dialog and return the chosen path."""

    def pick_folder(self, start: str | None = None) -> FolderPickResult:
        cmd = _pick_cmd(start)
        if cmd is None:
            return FolderPickResult(available=False, path=None)
        try:
            # Blocking: a modal dialog returns only when the user picks/cancels.
            # The HTTP layer runs this in a worker thread (asyncio.to_thread).
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except OSError:
            # The tool vanished between the which() probe and the spawn.
            return FolderPickResult(available=False, path=None)
        if proc.returncode == 0:
            picked = proc.stdout.strip()
            return FolderPickResult(available=True, path=picked or None)
        # A non-zero exit from a present dialog tool means the user cancelled.
        return FolderPickResult(available=True, path=None)


def _pick_cmd(start: str | None) -> list[str] | None:
    """The native folder-dialog argv for this host, or None if none is available."""
    if sys.platform == "darwin":
        location = ""
        if start:
            # Escape for the AppleScript string literal (path → POSIX file).
            esc = start.replace("\\", "\\\\").replace('"', '\\"')
            location = f' default location (POSIX file "{esc}")'
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
