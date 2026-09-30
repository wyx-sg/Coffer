"""Stop every process in one process group: SIGTERM, a short grace, SIGKILL.

A stdio MCP server is started in its own session (the SDK passes
``start_new_session=True``), so its pid is its group's id and everything it
forks stays in that group unless it deliberately leaves. ``killpg`` reaches
every member at once, including a grandchild whose parent already exited —
which walking the leader's descendants cannot, since an orphan is re-parented
away from it.

Synchronous on purpose: it is called from a connection's teardown, which must
add no await point after the SDK's own close (see ``subprocess._cleanup``). The
grace is short; the common case is a group already gone, which returns at once.
"""

from __future__ import annotations

import contextlib
import os
import signal
import time

from coffer.infrastructure.platform.host import HostOs, host_os

#: How long members get to exit after SIGTERM before SIGKILL.
DEFAULT_GRACE_SECONDS = 1.0
_POLL_SECONDS = 0.02


def _alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # EPERM is ambiguous (a zombie or a foreign-euid member); keep going.
        return True
    return True


def kill_process_group(pgid: int, *, grace_seconds: float = DEFAULT_GRACE_SECONDS) -> bool:
    """Terminate the group ``pgid``. Returns True when it is gone afterwards.

    A no-op returning True on Windows (the SDK's job object covers it there)
    and for a group that no longer exists.
    """
    if host_os() is HostOs.WINDOWS or pgid <= 1:  # pragma: no cover - POSIX only
        return True
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except PermissionError:
        pass
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if not _alive(pgid):
            return True
        time.sleep(_POLL_SECONDS)
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pgid, signal.SIGKILL)
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if not _alive(pgid):
            return True
        time.sleep(_POLL_SECONDS)
    return not _alive(pgid)


__all__ = ["DEFAULT_GRACE_SECONDS", "kill_process_group"]
