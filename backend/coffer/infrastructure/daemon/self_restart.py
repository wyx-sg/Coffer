"""A daemon restarting itself: start a successor, then exit (spec daemon
"Restart itself on request").

The desktop shell and ``coffer daemon restart`` restart the daemon from the
outside — stop it, watch the port free, spawn a new one. A page in a browser
has no outside: it is served *by* the daemon. So the daemon does the same two
halves itself, in the order that keeps them a true restart:

1. it spawns its successor — the same command every surface spawns
   (``spawn.daemon_spawn_command``), detached, with this process's own
   environment — carrying :data:`PREDECESSOR_ENV`, this daemon's pid;
2. it then exits through the ordinary graceful path (the shutdown signal);
3. the successor, before it takes the spawn lock or binds anything, waits for
   that pid to be gone (:func:`await_predecessor`) and only then starts as any
   daemon does — binding the port the pre-bind config names, so a port saved
   on Settings → Daemon applies here, and minting a fresh token.

Nothing new decides where the daemon comes from, which port it binds or
whether a second one may run: the successor goes through the same
``bootstrap.acquire_or_existing`` as every start. If the predecessor never
exits, the successor forces it out (``force_stop``, through ``on_timeout``):
the user asked for this daemon to be replaced, and a wedged one would otherwise
keep its port and make the restart fail beside it.

The frozen build is one PyInstaller one-file executable. A one-file program
that starts *itself* again must say so (``PYINSTALLER_RESET_ENVIRONMENT``), or
the child takes the parent's unpacked files for its own and loses them when the
parent exits. Why launchd is not asked instead: its login service restarts
only an exit that failed (``login_service``), is installed only when Start at
login is on, and throttles a restart by seconds; the successor works the same
whichever way the daemon was started.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from collections.abc import Callable, Mapping, MutableMapping

import psutil

from coffer.infrastructure.daemon.spawn import spawn_detached_daemon

_logger = logging.getLogger(__name__)

#: The pid the successor waits on. Removed from the environment as soon as it
#: is read, so nothing the successor spawns inherits it.
PREDECESSOR_ENV = "COFFER_DAEMON_PREDECESSOR_PID"
#: PyInstaller's switch for a one-file program that starts itself again.
_PYINSTALLER_RESET = "PYINSTALLER_RESET_ENVIRONMENT"

#: Long enough for a graceful exit — uvicorn's ten-second grace for open
#: connections plus the lifespan's teardown — with room to spare.
PREDECESSOR_TIMEOUT_SECONDS = 60.0
_POLL_SECONDS = 0.1


def successor_env(environ: Mapping[str, str], pid: int, *, frozen: bool) -> dict[str, str]:
    """The successor's environment: this daemon's own, plus the pid to wait on."""
    env = dict(environ)
    env[PREDECESSOR_ENV] = str(pid)
    if frozen:
        env[_PYINSTALLER_RESET] = "1"
    else:
        env.pop(_PYINSTALLER_RESET, None)
    return env


def spawn_successor() -> int:
    """Start this daemon's successor, detached; its pid. Raises ``OSError``."""
    env = successor_env(os.environ, os.getpid(), frozen=bool(getattr(sys, "frozen", False)))
    proc = spawn_detached_daemon(env=env)
    _logger.info("daemon.restart.successor_spawned", extra={"successor_pid": proc.pid})
    return proc.pid


def process_is_gone(pid: int) -> bool:
    """Whether ``pid`` has exited. A zombie has: it holds no port and no files,
    and only its parent — never this process — can reap it."""
    try:
        return psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return True
    except psutil.Error:
        return False


def await_predecessor(
    environ: MutableMapping[str, str],
    *,
    gone: Callable[[int], bool] = process_is_gone,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    timeout: float = PREDECESSOR_TIMEOUT_SECONDS,
    on_timeout: Callable[[int], object] | None = None,
) -> bool:
    """Wait for the daemon this one succeeds to exit; ``True`` once it has.

    A start that is not a restart carries no predecessor and returns at once.
    A malformed value is ignored. On a timeout ``on_timeout`` gets the pid —
    the entry point forces the wedged predecessor out there — and this returns
    ``False``; the caller starts anyway, and the spawn lock and the liveness
    probe decide as for any start.
    """
    raw = environ.pop(PREDECESSOR_ENV, None)
    if raw is None:
        return True
    try:
        pid = int(raw)
    except ValueError:
        _logger.warning("daemon.restart.bad_predecessor", extra={"value": raw})
        return True
    deadline = clock() + timeout
    while not gone(pid):
        if clock() >= deadline:
            _logger.warning("daemon.restart.predecessor_still_running", extra={"pid": pid})
            if on_timeout is not None:
                on_timeout(pid)
            return False
        sleep(_POLL_SECONDS)
    return True


__all__ = [
    "PREDECESSOR_ENV",
    "PREDECESSOR_TIMEOUT_SECONDS",
    "await_predecessor",
    "process_is_gone",
    "spawn_successor",
    "successor_env",
]
