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
import subprocess
import sys
from pathlib import Path

from coffer.infrastructure.logging.files import log_dir

#: Where the macOS desktop bundle stages its `coffer-daemon`: the .dmg ships
#: `coffer-daemon` as a Tauri sidecar (`externalBin` in
#: `desktop/tauri.conf.json`), which lands in `Contents/MacOS/`. So on a machine
#: whose Coffer came from the .app rather than the CLI tarball, this is where the
#: daemon actually is, and the probe is a live resolution step — not a
#: compatibility shim. Module-level so tests can monkeypatch it.
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
        3. macOS only: the daemon staged inside the installed desktop
           bundle (``/Applications/Coffer.app/Contents/MacOS/coffer-daemon``)
           — where the .dmg puts it, so a machine that installed Coffer as an
           app rather than a CLI tarball resolves here.

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


def daemon_log_path() -> Path:
    """Where a detached daemon's stdout/stderr land — ``~/.coffer/logs/daemon.log``."""
    return log_dir() / "daemon.log"


def spawn_detached_daemon() -> subprocess.Popen[bytes]:
    """Spawn the daemon detached from the caller, stdio redirected to ``daemon.log``.

    The one spawn every auto-spawn surface shares — the CLI's detect-or-spawn,
    ``coffer daemon start`` and the shim — so they all keep the daemon's own
    refusals. The daemon prints why it would not start (a squatted fixed port,
    say) to stderr and exits; a spawner that sent stderr to ``DEVNULL`` (as the
    shim once did) threw that away and could only report "did not come up
    within 10s". Appending both streams to ``daemon.log`` keeps the message
    where "check daemon.log" already points the user.

    Raises ``OSError`` when the process cannot be started; the log handle is
    closed on that path and otherwise leaks into the child on purpose.
    """
    log_path = daemon_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = open(log_path, "ab")  # noqa: SIM115 — handle leaks intentionally into child
    kwargs: dict[str, object] = {
        "stdout": log,
        "stderr": log,
        "stdin": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
        )
    else:
        kwargs["start_new_session"] = True
    try:
        return subprocess.Popen(daemon_spawn_command(), **kwargs)  # type: ignore[call-overload,no-any-return]
    except OSError:
        log.close()
        raise
