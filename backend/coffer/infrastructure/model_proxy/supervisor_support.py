"""Small pieces of the proxy supervisor: its status, the spawn command, process checks."""

from __future__ import annotations

import contextlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from coffer.infrastructure.daemon.spawn import daemon_spawn_command


@dataclass(frozen=True)
class ProxyStatus:
    running: bool
    pid: int | None
    port: int
    version: str | None
    restarts: int
    last_error: str | None
    revision: int | None
    started_at: str | None
    #: Consecutive failed attempts to start it; ``0`` while it is up or idle.
    consecutive_failures: int = 0
    #: The start has failed ``FAILING_AFTER`` times running; retries slow down.
    failing: bool = False


def default_proxy_command(port: int) -> list[str]:
    """The frozen ``coffer-daemon proxy`` or, from source, this interpreter."""
    if getattr(sys, "frozen", False):
        return [daemon_spawn_command()[0], "proxy", "--port", str(port)]
    return [sys.executable, "-m", "coffer.infrastructure.model_proxy.entry", "--port", str(port)]


def source_root() -> str:
    """The directory holding the imported ``coffer`` package — prefixed onto the
    child's ``PYTHONPATH`` so a worktree's proxy runs that worktree's code."""
    import coffer

    return str(Path(coffer.__file__).resolve().parent.parent)


def pid_alive(pid: int) -> bool:
    # A proxy an earlier supervisor in this same process spawned is our child:
    # once it exits it stays a zombie — and "alive" to kill(0) — until reaped.
    with contextlib.suppress(ChildProcessError, OSError):
        os.waitpid(pid, os.WNOHANG)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
