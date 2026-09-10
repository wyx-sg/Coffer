"""Frozen-aware daemon spawn command resolution (ADR daemon-detect-or-spawn).

``daemon_spawn_command()`` is a pure, importable function that returns the
correct subprocess command list to launch ``coffer-daemon``, regardless of
whether the process is running from source (dev/pip) or as a frozen
PyInstaller bundle.

Both ``coffer daemon start`` (``surfaces.cli.daemon_cmd``) and the CLI's
detect-or-spawn path (``surfaces.cli._client``) import from here so the
resolution logic lives in exactly one place.

Import rules:
- This module is in ``coffer.infrastructure``.
- ``coffer.infrastructure`` may NOT import ``coffer.surfaces`` (Contract 2).
- Callers in ``surfaces`` import this module — that direction is fine.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

#: Where the retired macOS desktop bundle staged its `coffer-daemon`. Coffer
#: no longer ships that bundle, but a machine that installed one still has it
#: at this stable path, so the probe is kept as an upgrade courtesy: it costs
#: one `exists()` and saves a user with an old /Applications/Coffer.app from a
#: shim that cannot find a daemon. Module-level so tests can monkeypatch it.
_MACOS_APP_BUNDLE_DAEMON = Path("/Applications/Coffer.app/Contents/MacOS/coffer-daemon")


def daemon_spawn_command() -> list[str]:
    """Return the subprocess command to spawn the Coffer daemon.

    - **Not frozen** (dev / ``pip install``): returns
      ``[sys.executable, '-m', 'coffer.infrastructure.daemon.entry']``.
    - **Frozen** (PyInstaller): the running binary is ``coffer`` /
      ``coffer-mcp-shim``; the companion daemon binary is resolved by
      probing, in order:

        1. the sibling ``coffer-daemon`` (or ``.exe``) next to
           ``sys.executable`` — the CLI-tarball layout, where the installer
           co-locates all three binaries in ``~/.coffer/bin``;
        2. ``coffer-daemon`` on ``PATH`` (``shutil.which``) — covers separate
           installs and any layout where the bin dir is exported;
        3. macOS only: the daemon staged inside a previously-installed
           desktop bundle
           (``/Applications/Coffer.app/Contents/MacOS/coffer-daemon``) — a
           leftover from the retired desktop app, kept so a machine that
           still has one is not stranded.

      The first candidate that exists wins. If none exists, the sibling
      path is returned as a best effort so the caller surfaces a single,
      clear "failed to spawn daemon" error pointing at the log.
    """
    if getattr(sys, "frozen", False):
        # PyInstaller sets sys.frozen = True and sys.executable to the
        # frozen binary's path.
        name = "coffer-daemon.exe" if sys.platform == "win32" else "coffer-daemon"
        sibling = Path(sys.executable).resolve().parent / name
        if sibling.exists():
            return [str(sibling)]
        on_path = shutil.which(name)
        if on_path:
            return [on_path]
        if sys.platform == "darwin" and _MACOS_APP_BUNDLE_DAEMON.is_file():
            return [str(_MACOS_APP_BUNDLE_DAEMON)]
        return [str(sibling)]

    return [sys.executable, "-m", "coffer.infrastructure.daemon.entry"]
