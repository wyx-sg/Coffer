"""Stop a daemon that will not stop on its own — the force half of a restart.

A restart the user asks for (``coffer daemon restart``, the web UI's restart,
the desktop shell's) means "replace the daemon that is there". When that daemon
is wedged it never finishes its graceful exit, keeps its port, and the
replacement can only refuse beside it: the restart fails and the wedged process
stays forever. So a restart escalates — ``SIGTERM``, a grace period, then
``SIGKILL`` of the whole tree — but only for a process it can prove is a Coffer
daemon serving this same vault (spec daemon "Force out a wedged daemon on an
explicit restart"). Automatic starts never come here: a CLI command or a shim
that finds the daemon busy waits or gives up, it does not kill.
"""

from __future__ import annotations

import contextlib
import logging
import os
import signal
import time
from collections.abc import Callable
from typing import Literal

import psutil

from coffer.infrastructure.daemon.orphan_sweep import _protected_pids, serves_our_vault
from coffer.infrastructure.daemon.self_restart import process_is_gone

_logger = logging.getLogger(__name__)

#: How long a stopping daemon gets to exit by itself: uvicorn's ten-second
#: grace for open connections, the one-second draining window and the
#: lifespan's teardown, with a little room.
GRACEFUL_STOP_SECONDS = 15.0
_POLL_SECONDS = 0.1

StopOutcome = Literal["gone", "not_ours", "stopped", "killed"]


def _wait_gone(
    pid: int, timeout: float, *, clock: Callable[[], float], sleep: Callable[[float], None]
) -> bool:
    deadline = clock() + timeout
    while not process_is_gone(pid):
        if clock() >= deadline:
            return False
        sleep(_POLL_SECONDS)
    return True


def _kill_tree_sparing_us(proc: psutil.Process, *, timeout: float = 2.0) -> None:
    """SIGKILL ``proc`` and its descendants, except this process and its
    ancestors. A restart's successor is itself a descendant of the daemon it
    replaces — the predecessor spawned it — so a plain tree kill would take
    the successor down with the wedged daemon."""
    spared = _protected_pids(os.getpid())
    try:
        targets = proc.children(recursive=True)
    except psutil.Error:
        targets = []
    targets = [p for p in [*targets, proc] if p.pid not in spared]
    for p in targets:
        with contextlib.suppress(psutil.Error):
            p.kill()
    psutil.wait_procs(targets, timeout=timeout)


def stop_daemon_process(
    pid: int,
    *,
    grace: float = GRACEFUL_STOP_SECONDS,
    already_signalled: bool = False,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> StopOutcome:
    """Make the daemon ``pid`` exit, escalating to ``SIGKILL`` after ``grace``.

    ``"gone"`` — it had already exited. ``"not_ours"`` — it is not a Coffer
    daemon of this vault, and was not touched. ``"stopped"`` — it exited
    within the grace period. ``"killed"`` — it did not, and its process tree
    was killed. ``already_signalled`` skips the ``SIGTERM`` for a caller that
    has asked it to stop another way (the shutdown route, its own signal).
    """
    if process_is_gone(pid):
        return "gone"
    if not serves_our_vault(pid):
        return "not_ours"
    if not already_signalled:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return "gone"
    if _wait_gone(pid, grace, clock=clock, sleep=sleep):
        return "stopped"
    _logger.warning("daemon.force_stop", extra={"pid": pid, "grace_seconds": grace})
    try:
        _kill_tree_sparing_us(psutil.Process(pid))
    except psutil.NoSuchProcess:
        return "stopped"
    return "killed"


__all__ = ["GRACEFUL_STOP_SECONDS", "StopOutcome", "stop_daemon_process"]
