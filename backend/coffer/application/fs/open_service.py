"""Local-filesystem open / reveal actions for the read-only file viewers.

Spec daemon "Open and reveal existing absolute paths" (ADR daemon-proxies-os-file-actions). Coffer's
file viewers are read-only; the user edits in their own tools. On the desktop
the packaged app reaches the OS directly, but the web surface can't — so it
asks the loopback daemon, which is *always co-located with the web client on
the user's own machine*, to do it.

``open_path`` launches an existing path in an application (the user's preferred
editor, or the OS default); ``reveal_path`` selects it in the OS file manager.
Read-only directory browsing is :class:`FsBrowseService`'s job; this is the
acting-on-an-existing-path counterpart.

``open_url`` hands a web link (``http``, ``https`` or ``mailto`` only) to the
default browser, for the links in a document the desktop app's webview shows.

Safety: every path is validated **absolute and existing** before any process is
spawned, and the launcher is invoked with an **argument vector** (never a shell
string — no interpolation). The daemon never creates anything here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from coffer.application.platform_port import PlatformPort
from coffer.domain.errors import FsPathNotOpenable


class FsOpenService:
    """Open or reveal an existing absolute path on the host OS.

    Which launcher argv does it is the host's answer (``PlatformPort``); this
    service owns validation and the detached spawn.
    """

    def __init__(self, platform: PlatformPort) -> None:
        self._platform = platform

    def open(self, path: str, with_app: str | None = None) -> None:
        """Open ``path`` in ``with_app`` (an app name/path) or the OS default."""
        target = _validated(path)
        self._spawn(self._platform.open_command(target, with_app), target)

    def reveal(self, path: str) -> None:
        """Select / reveal ``path`` in the OS file manager."""
        target = _validated(path)
        self._spawn(self._platform.reveal_command(target), target)

    def open_url(self, url: str) -> None:
        """Open a web link in the default browser: a link in a document the
        desktop app shows, which its webview does not open by itself."""
        checked = _web_link(url)
        self._spawn(self._platform.url_command(checked), Path(checked))

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


#: The only links handed to the browser: never ``file:``, ``javascript:`` or an
#: app's own scheme, which would make this route a way to launch anything.
_WEB_SCHEMES = ("http", "https", "mailto")
_MAX_URL = 8192


def _web_link(url: str) -> str:
    parts = urlsplit(url)
    if (
        parts.scheme.lower() not in _WEB_SCHEMES
        or (parts.scheme.lower() != "mailto" and not parts.netloc)
        or len(url) > _MAX_URL
        or any(ch.isspace() or ord(ch) < 32 for ch in url)
    ):
        raise FsPathNotOpenable(url[:200], "not_a_web_link")
    return url


def _validated(path: str) -> Path:
    if not path or not Path(path).is_absolute():
        raise FsPathNotOpenable(path, "not_absolute")
    target = Path(path)
    if not target.exists():
        raise FsPathNotOpenable(path, "not_found")
    return target
