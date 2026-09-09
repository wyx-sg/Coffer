"""Best-effort cleanup of subprocess orphans left by a previous daemon crash."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

_logger = logging.getLogger(__name__)


def _pid_dir() -> Path:
    return Path(os.environ.get("HOME", "~")).expanduser() / ".coffer" / "upstream-pids"


def record_spawn(server_name: str, pid: int, command_line: list[str]) -> Path:
    """Called by spawn_and_initialize after the SDK has spawned the upstream."""
    pid_dir = _pid_dir()
    pid_dir.mkdir(parents=True, exist_ok=True)
    path = pid_dir / f"{server_name}-{pid}.json"
    path.write_text(
        json.dumps(
            {
                "server": server_name,
                "pid": pid,
                "command_line": command_line,
                "spawned_at": datetime.now(tz=UTC).isoformat(),
            }
        )
    )
    return path


def _kill_proc_tree(proc: psutil.Process, *, timeout: float = 2.0) -> None:
    """SIGTERM then SIGKILL ``proc`` and every descendant.

    The real upstream is a ``uv tool uvx <server>`` wrapper that spawns a
    python grandchild; killing only the recorded wrapper PID leaves that
    grandchild reparented to launchd and alive. Enumerate descendants BEFORE
    signalling the root so a child that reparents mid-kill is still reaped.
    """
    try:
        targets = proc.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        targets = []
    targets.append(proc)

    for p in targets:
        with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            p.terminate()

    _gone, alive = psutil.wait_procs(targets, timeout=timeout)
    for p in alive:
        with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            p.kill()


def reap_pidfile(path: Path) -> bool:
    """Kill the process tree recorded in ``path`` (if still live & matching),
    then remove the file.

    Returns True iff a live process whose command line still matches the
    recorded one was found and killed. Already-dead PIDs, PID-recycled
    strangers (cmdline mismatch), and malformed files are silently dropped.
    Shared by ``sweep_orphans`` (startup) and the upstream connection's
    ``close()`` (belt-and-braces when the SDK teardown fails to reap).
    """
    try:
        payload: dict[str, Any] = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        path.unlink(missing_ok=True)
        return False

    pid = payload.get("pid")
    expected_cmd = payload.get("command_line", [])
    if not isinstance(pid, int):
        path.unlink(missing_ok=True)
        return False

    try:
        proc = psutil.Process(pid)
        actual_cmd = proc.cmdline()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        # PID is dead or unreachable — drop the file
        path.unlink(missing_ok=True)
        return False

    # Verify the command line still matches — guards against PID recycling.
    if list(actual_cmd) != list(expected_cmd):
        path.unlink(missing_ok=True)
        return False

    killed = False
    try:
        _kill_proc_tree(proc)
        killed = True
        _logger.info(
            "orphan_sweep.killed",
            extra={"server": payload.get("server"), "pid": pid},
        )
    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
        _logger.warning("orphan_sweep.kill_failed", extra={"pid": pid, "error": str(e)})

    path.unlink(missing_ok=True)
    return killed


def sweep_orphans() -> int:
    """Walk ~/.coffer/upstream-pids/, kill matching live processes, remove files.

    Returns the number of orphans killed.
    """
    pid_dir = _pid_dir()
    if not pid_dir.exists():
        return 0

    return sum(reap_pidfile(path) for path in list(pid_dir.glob("*.json")))


def _exe_basename(proc: psutil.Process) -> str | None:
    """Basename of ``proc``'s executable, or ``None`` when it can't be read."""
    try:
        exe = proc.exe()
    except (psutil.Error, OSError):
        return None
    return os.path.basename(exe) if exe else None


def _protected_pids(pid: int) -> set[int]:
    """``pid`` plus every ancestor pid — the processes a daemon must NEVER reap:
    itself, its PyInstaller bootloader parent (same executable!), the desktop app
    that launched it, and launchd/init."""
    protected = {pid}
    with contextlib.suppress(psutil.Error):
        for ancestor in psutil.Process(pid).parents():
            protected.add(ancestor.pid)
    return protected


def _select_stale_daemons(
    candidates: Iterable[tuple[int, str | None]],
    *,
    protected: set[int],
    own_exe_basename: str,
) -> list[int]:
    """Pure selection: pids running our own daemon executable that are neither us
    nor an ancestor. Split from :func:`reap_stale_daemons` so the decision is
    unit-testable without enumerating or killing real processes."""
    return [pid for pid, base in candidates if pid not in protected and base == own_exe_basename]


def reap_stale_daemons() -> int:
    """Terminate any OTHER process running this daemon's executable (ADR-006).

    Called by the winning daemon at startup: it has just bound the port under the
    spawn lock because ``live_daemon()`` found nobody serving, so any process
    sharing our executable is a stale/wedged sibling a prior app launch or crash
    left behind — reap it. The ADR-006 flock means a racing spawn is blocked, not
    mid-bind, so it is never a legitimate target.

    **Frozen builds only.** In a source run ``sys.executable`` is the Python
    interpreter, and matching its basename would target unrelated interpreters;
    there we no-op. Best-effort — a process that dies mid-sweep is ignored, and
    nothing here raises to the caller. Returns the number of trees reaped.
    """
    if not getattr(sys, "frozen", False):
        return 0
    own_base = os.path.basename(sys.executable)
    protected = _protected_pids(os.getpid())
    procs = list(psutil.process_iter())
    stale = set(
        _select_stale_daemons(
            ((p.pid, _exe_basename(p)) for p in procs),
            protected=protected,
            own_exe_basename=own_base,
        )
    )
    killed = 0
    for proc in procs:
        if proc.pid not in stale:
            continue
        try:
            _kill_proc_tree(proc)
            killed += 1
            _logger.info("daemon.reaped_stale_sibling", extra={"pid": proc.pid})
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            _logger.warning("daemon.reap_stale_failed", extra={"pid": proc.pid, "error": str(e)})
    return killed


def startup_sweep() -> tuple[int, int]:
    """All startup process hygiene in one call, for the winning daemon: reap
    leaked MCP upstreams from a prior crash AND stale sibling daemons a prior app
    launch left running. Returns ``(upstreams_killed, daemons_reaped)``."""
    return sweep_orphans(), reap_stale_daemons()
