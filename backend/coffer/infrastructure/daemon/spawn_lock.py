"""The spawn lock: ``~/.coffer/daemon.lock``, the flock every daemon start takes
before it probes, binds and publishes (ADR daemon-detect-or-spawn).

Split out of :mod:`bootstrap`, which holds the critical section the lock
guards. The wait for it is bounded (spec daemon "Keep exactly one daemon per
vault"): a start never queues forever behind a boot that is not finishing.
"""

from __future__ import annotations

import contextlib
import os
import time
from collections.abc import Callable
from pathlib import Path

from coffer.infrastructure.vault.home import daemon_lock_path


def spawn_lock_path() -> Path:
    return daemon_lock_path()


#: How long a start waits for the spawn lock before it gives up and exits. The
#: holder is a daemon booting under the lock (migrations, the secret store, the
#: first vault scan), which takes seconds on a real vault; two minutes covers a
#: slow migration with room to spare. Without a bound, a holder that hangs makes
#: every later start — each CLI command, shim, desktop launch and launchd
#: restart — queue on the lock for good, which is how one wedged boot turned
#: into a pile of idle daemon processes (spec daemon "Keep exactly one daemon
#: per vault").
SPAWN_LOCK_TIMEOUT_SECONDS: float = 120.0
_SPAWN_LOCK_POLL_SECONDS: float = 0.2


class SpawnLockBusy(Exception):  # noqa: N818
    """Another start held the spawn lock for longer than this one would wait.

    Carries the pid the holder recorded in the lock file, when it could be
    read, so the refusal names who is starting.
    """

    def __init__(self, holder_pid: int | None, waited: float) -> None:
        self.holder_pid = holder_pid
        self.waited = waited
        who = f"pid {holder_pid}" if holder_pid is not None else "another process"
        super().__init__(
            f"another Coffer daemon ({who}) has been starting for over {waited:.0f}s; "
            "this start is exiting rather than queueing behind it"
        )


def _read_lock_holder(fd: int) -> int | None:
    """The pid the current lock holder wrote into the lock file, if readable."""
    try:
        raw = os.pread(fd, 32, 0)
        return int(raw.decode().strip() or "x")
    except (OSError, ValueError):
        return None


def _record_lock_holder(fd: int) -> None:
    """Write our pid into the lock file, for a waiter's refusal and for a person
    reading ``daemon.lock``. Best effort: the lock is the flock, not the text."""
    with contextlib.suppress(OSError):
        os.ftruncate(fd, 0)
        os.pwrite(fd, f"{os.getpid()}\n".encode(), 0)


def acquire_spawn_lock(
    timeout: float = SPAWN_LOCK_TIMEOUT_SECONDS,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Open ``~/.coffer/daemon.lock`` and take an exclusive ``flock``; return fd.

    Detect-or-spawn: this is the lock that serialises the probe+bind+write+announce
    critical section so two racing auto-spawns can't both bind. The caller MUST
    eventually free it via :func:`release_spawn_lock`. On Windows (no
    ``fcntl``) the lock degrades to a bare open fd — the daemon's own
    ``live_daemon`` refusal in ``bootstrap.acquire_or_existing`` plus the atomic
    ``os.replace`` remain as the last line of defence there.

    The wait is bounded by ``timeout``: past it the lock holder is a boot that
    is not finishing, and queueing behind it only adds one more idle process,
    so :class:`SpawnLockBusy` is raised and the caller exits.

    The lockfile itself is intentionally left on disk between runs — a flock is
    advisory and tied to the open fd, not the file's existence.
    """
    lock_path = spawn_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        import fcntl
    except ImportError:  # pragma: no cover - Windows fallback
        return fd
    deadline = clock() + timeout
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if clock() >= deadline:
                    raise SpawnLockBusy(_read_lock_holder(fd), timeout) from None
                sleep(_SPAWN_LOCK_POLL_SECONDS)
    except BaseException:
        os.close(fd)
        raise
    _record_lock_holder(fd)
    return fd


def release_spawn_lock(fd: int) -> None:
    """Release the ``flock`` and close ``fd`` (best-effort; safe if already gone)."""
    try:
        import fcntl
    except ImportError:  # pragma: no cover - Windows fallback
        pass
    else:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
    with contextlib.suppress(OSError):
        os.close(fd)
