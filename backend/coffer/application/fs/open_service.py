"""Local-filesystem open / reveal actions for the read-only file viewers.

Spec 004-agent-registry FR-039 (ADR-033). Coffer's file viewers are read-only;
the user edits in their own tools. On the desktop the packaged app reaches the
OS directly, but the web surface can't — so it asks the loopback daemon, which
is *always co-located with the web client on the user's own machine*, to do it.

``open_path`` launches an existing path in an application (the user's preferred
editor, or the OS default); ``reveal_path`` selects it in the OS file manager.
Read-only directory browsing is :class:`FsBrowseService`'s job; this is the
acting-on-an-existing-path counterpart.

Safety: every path is validated **absolute and existing** before any process is
spawned, and the launcher is invoked with an **argument vector** (never a shell
string — no interpolation). The daemon never creates anything here.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from coffer.domain.errors import FsPathNotOpenable


class FsOpenService:
    """Open or reveal an existing absolute path on the host OS."""

    def open(self, path: str, with_app: str | None = None) -> None:
        """Open ``path`` in ``with_app`` (an app name/path) or the OS default."""
        target = _validated(path)
        self._spawn(_open_cmd(target, with_app), target)

    def reveal(self, path: str) -> None:
        """Select / reveal ``path`` in the OS file manager."""
        target = _validated(path)
        self._spawn(_reveal_cmd(target), target)

    @staticmethod
    def _spawn(cmd: list[str], target: Path) -> None:
        # Fire-and-forget: the launcher (`open` / `xdg-open` / `explorer`) returns
        # immediately, and a long-lived editor must not hold the daemon. Detach so
        # the child outlives the request; only a failed *spawn* is an error.
        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as e:
            raise FsPathNotOpenable(str(target), "launch_failed") from e


def _validated(path: str) -> Path:
    if not path or not Path(path).is_absolute():
        raise FsPathNotOpenable(path, "not_absolute")
    target = Path(path)
    if not target.exists():
        raise FsPathNotOpenable(path, "not_found")
    return target


def _open_cmd(target: Path, with_app: str | None) -> list[str]:
    s = str(target)
    app = (with_app or "").strip()
    if sys.platform == "darwin":
        # No editor chosen → `open -t` opens the default *text* editor. Plain
        # `open <file>` fails (kLSApplicationNotFoundErr) for file types with no
        # registered default app — common for the extensionless config files
        # Coffer manages — and the non-zero exit is swallowed, so nothing opens.
        return ["open", "-a", app, s] if app else ["open", "-t", s]
    if sys.platform == "win32":
        # `start` needs an empty title arg; an explicit app is launched directly.
        return [app, s] if app else ["cmd", "/c", "start", "", s]
    # Linux / other: a chosen editor is launched directly; otherwise xdg-open.
    return [app, s] if app else ["xdg-open", s]


def _reveal_cmd(target: Path) -> list[str]:
    s = str(target)
    if sys.platform == "darwin":
        return ["open", "-R", s]
    if sys.platform == "win32":
        return ["explorer", f"/select,{s}"]
    # Linux has no portable "select the file" — degrade to opening the folder.
    folder = target if target.is_dir() else target.parent
    return ["xdg-open", str(folder)]
