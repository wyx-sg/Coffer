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

**Nothing here boots a loaded job out**, and that is the rule that keeps this
module from being the most destructive thing in Coffer. Once the agent has
started the daemon, the running daemon *is* the launchd job — so
``launchctl bootout`` terminates it. The install and the uninstall are both
reached from the Settings page, which is served BY that daemon: booting out
would kill the process answering the request, so the reply never arrives, the
switch reverts over a change that did happen, and the replacement mints a
token the open page does not have. Writing or deleting the plist is enough for
"does it start at login", which is the whole question; a job already loaded
stays loaded until the user logs out, and a crash in the meantime is one more
restart rather than a problem.
"""

from __future__ import annotations

import logging
import os
import plistlib
import subprocess
import sys
from pathlib import Path

from coffer.infrastructure.daemon.spawn import daemon_spawn_command
from coffer.infrastructure.logging.files import log_dir

_logger = logging.getLogger(__name__)

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


#: How long the login-shell probe is allowed to take. A shell profile that
#: hangs must not hang an install; the inherited PATH is a worse answer, not
#: no answer.
_SHELL_PROBE_TIMEOUT = 3.0


def login_shell_path() -> str:
    """The user's real `PATH`, as their login shell reports it.

    Not `os.environ["PATH"]`, and the difference is the whole point of the
    key. This code usually runs *inside the daemon* — reached from the
    Settings page — and that daemon was commonly auto-spawned by an MCP shim
    belonging to a GUI-launched editor, whose `PATH` is the truncated one
    macOS hands a Dock launch. Baking that into the agent would install
    exactly the minimal `PATH` this key exists to avoid, and the `npx`/`uvx`
    upstreams would resolve to nothing at the next login.

    The shell is asked the same way `desktop/src/env_path.rs` asks it, and
    falls back to the inherited value on any failure: a probe that cannot
    answer must not stop an install.
    """
    shell = os.environ.get("SHELL", "/bin/zsh")
    inherited = os.environ.get("PATH", "")
    try:
        result = subprocess.run(
            [shell, "-l", "-c", 'printf %s "$PATH"'],
            capture_output=True,
            text=True,
            timeout=_SHELL_PROBE_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        _logger.warning("login shell PATH probe failed (%r); using the inherited PATH", exc)
        return inherited
    probed = result.stdout.strip()
    return probed or inherited


def _launchctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["launchctl", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _domain() -> str:
    return f"gui/{os.getuid()}"


def _is_loaded() -> bool:
    """Whether launchd currently holds this label in the user's GUI domain."""
    return _launchctl("print", f"{_domain()}/{LABEL}").returncode == 0


def install() -> Path:
    """Write the agent, and load it when launchd does not already hold it.

    Idempotent, and deliberately gentle: an agent that is already loaded is
    left loaded and the rewritten plist takes effect at the next login. The
    alternative — boot it out and bootstrap the new one — reloads a *running
    daemon*, which on this machine is usually the process running this code.
    """
    if not is_supported():
        raise ServiceUnsupported("a login service is macOS-only; there is no launchd here")
    path = plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_plist(
        program=daemon_spawn_command(),
        path_env=login_shell_path(),
        log_file=log_dir() / "daemon.log",
    )
    path.write_bytes(plistlib.dumps(payload))
    if _is_loaded():
        return path
    result = _launchctl("bootstrap", _domain(), str(path))
    if result.returncode != 0:
        # Older systems answer `load -w` and not much else.
        _launchctl("load", "-w", str(path))
    return path


def uninstall() -> bool:
    """Remove the agent. False when there was nothing installed.

    Removes the plist and stops there. "Stop starting it at login" is not
    "stop it now", and the running daemon is very often the loaded job — so
    unloading here would shut Coffer down on the way to a settings change.
    launchd forgets the job at the next login, which is exactly when the
    setting was going to matter.
    """
    if not is_supported():
        raise ServiceUnsupported("a login service is macOS-only; there is no launchd here")
    path = plist_path()
    if not path.exists():
        return False
    path.unlink(missing_ok=True)
    return True
