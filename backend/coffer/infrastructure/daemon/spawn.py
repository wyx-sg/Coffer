"""Frozen-aware daemon spawn command resolution — ADR-006.

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
           installs and any layout where the bin dir is exported.

      The first candidate that exists wins. If neither exists, the sibling
      path is returned as a best effort so the caller surfaces a single,
      clear "failed to spawn daemon" error pointing at the log. (In the
      desktop app the Tauri shell is the daemon's lifecycle manager and spawns
      it from the bundle, so the shim's auto-spawn is only the fallback path.)
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
        return [str(sibling)]

    return [sys.executable, "-m", "coffer.infrastructure.daemon.entry"]
