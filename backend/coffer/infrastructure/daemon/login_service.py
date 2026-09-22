"""The daemon as a login service: a launchd agent that starts it and keeps it.

Coffer's daemon is what an agent talks to, and agents work in terminals, in
editors, over a chat channel — mostly with no Coffer window open anywhere. A
daemon that only exists because something started it is therefore down exactly
when it is wanted, and every client's answer to that ("start one myself") is a
five-to-fifteen-second cold start paid by whoever happened to ask first.

launchd is the fix macOS already has. This module writes one user agent:

* ``RunAtLoad`` — it is up as soon as the user logs in, before anything asks.
* ``KeepAlive: {SuccessfulExit: false}`` — a crash is restarted, a clean exit
  is not. That asymmetry is load-bearing, not caution: the daemon stands down
  by *exiting cleanly* when nothing has wanted it for hours
  (:func:`coffer.infrastructure.daemon.entry._stand_down_when_idle`), and a
  plain ``KeepAlive: true`` would restart it a second later, forever. Every
  client can start a daemon, so nothing is lost by letting a deliberate exit
  stand.
* ``EnvironmentVariables.PATH`` — captured from the shell that ran the
  install. A launchd agent otherwise inherits a minimal ``PATH``, and the
  daemon spawns ``npx`` / ``uvx`` MCP upstreams that then resolve to nothing.
  This is the same problem the desktop shell solves by probing the login shell
  (``desktop/src/env_path.rs``); here the install is already running in the
  user's own environment, so the honest source is that environment.

Installing is opt-in and reversible, and the plist names the binary it found
at install time rather than a launcher that re-resolves — an agent that
silently follows a symlink to a binary from another install is worse than one
that fails visibly and is reinstalled.
"""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

from coffer.infrastructure.daemon.spawn import daemon_spawn_command
from coffer.infrastructure.logging.files import log_dir

#: The launchd label, and the plist's basename. Reverse-DNS under the same
#: domain as the desktop bundle (`dev.coffer.desktop`), distinct from it
#: because they are different programs with different lifetimes.
LABEL = "dev.coffer.daemon"


class ServiceUnsupported(RuntimeError):  # noqa: N818
    """Raised where there is no launchd to install into."""


def is_supported() -> bool:
    """launchd is macOS's, and this agent is written for it alone."""
    return sys.platform == "darwin"


def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def is_installed() -> bool:
    return plist_path().exists()


def build_plist(*, program: list[str], path_env: str, log_file: Path) -> dict[str, object]:
    """The agent's contents, as a plain dict. Pure, so the decisions are testable.

    ``StandardOutPath``/``StandardErrorPath`` both point at the daemon log the
    CLI, the shell and the Activity page already read. A launchd agent that
    logged somewhere else would be a second place to look that nothing tells
    anyone about — the same rule ``desktop/src/logging.rs`` follows.
    """
    return {
        "Label": LABEL,
        "ProgramArguments": program,
        "RunAtLoad": True,
        # Restart a crash; let a deliberate stand-down stand. See the module
        # docstring — inverting this turns the idle shutdown into a restart loop.
        "KeepAlive": {"SuccessfulExit": False},
        "EnvironmentVariables": {"PATH": path_env, "HOME": str(Path.home())},
        "StandardOutPath": str(log_file),
        "StandardErrorPath": str(log_file),
    }


def _launchctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["launchctl", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _domain() -> str:
    return f"gui/{os.getuid()}"


def install() -> Path:
    """Write the agent and load it. Returns the plist path.

    Idempotent: an existing agent is booted out first, so reinstalling after
    an upgrade re-points it at the new binary rather than leaving the old one
    loaded.
    """
    if not is_supported():
        raise ServiceUnsupported("a login service is macOS-only; there is no launchd here")
    path = plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_plist(
        program=daemon_spawn_command(),
        path_env=os.environ.get("PATH", ""),
        log_file=log_dir() / "daemon.log",
    )
    # Boot out BEFORE rewriting: launchd holds the loaded copy, so a rewrite
    # alone would leave the previous program running until the next login.
    _launchctl("bootout", f"{_domain()}/{LABEL}")
    path.write_bytes(plistlib.dumps(payload))
    result = _launchctl("bootstrap", _domain(), str(path))
    if result.returncode != 0:
        # `bootstrap` fails on an already-loaded label; the bootout above makes
        # that unlikely, but older systems answer `load -w` and not much else.
        _launchctl("load", "-w", str(path))
    return path


def uninstall() -> bool:
    """Unload and remove the agent. False when there was nothing installed."""
    if not is_supported():
        raise ServiceUnsupported("a login service is macOS-only; there is no launchd here")
    path = plist_path()
    if not path.exists():
        return False
    _launchctl("bootout", f"{_domain()}/{LABEL}")
    _launchctl("unload", str(path))
    path.unlink(missing_ok=True)
    return True
