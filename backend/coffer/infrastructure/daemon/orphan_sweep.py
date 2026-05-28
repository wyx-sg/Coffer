"""Best-effort cleanup of subprocess orphans left by a previous daemon crash."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import signal
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


def forget_spawn(path: Path) -> None:
    """Called by close() on graceful shutdown."""
    with contextlib.suppress(OSError):
        path.unlink(missing_ok=True)


def sweep_orphans() -> int:
    """Walk ~/.coffer/upstream-pids/, kill matching live processes, remove files.

    Returns the number of orphans killed.
    """
    pid_dir = _pid_dir()
    if not pid_dir.exists():
        return 0

    killed = 0
    for path in list(pid_dir.glob("*.json")):
        try:
            payload: dict[str, Any] = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            path.unlink(missing_ok=True)
            continue

        pid = payload.get("pid")
        expected_cmd = payload.get("command_line", [])

        if not isinstance(pid, int):
            path.unlink(missing_ok=True)
            continue

        try:
            proc = psutil.Process(pid)
            actual_cmd = proc.cmdline()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            # PID is dead or unreachable — drop the file
            path.unlink(missing_ok=True)
            continue

        # Verify the command line still matches — guards against PID recycling
        if list(actual_cmd) != list(expected_cmd):
            path.unlink(missing_ok=True)
            continue

        # Real orphan — kill it
        try:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=2.0)
            except psutil.TimeoutExpired:
                proc.kill()
            killed += 1
            _logger.info(
                "orphan_sweep.killed",
                extra={"server": payload.get("server"), "pid": pid},
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            _logger.warning("orphan_sweep.kill_failed", extra={"pid": pid, "error": str(e)})

        path.unlink(missing_ok=True)

    return killed
