"""Daemon discovery file (~/.coffer/daemon.json) with restrictive permissions,
plus the pid check that says whether a recorded pid is still a Coffer daemon."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import psutil

from coffer.infrastructure.daemon.atomic_write import write_json_0600

#: Command-line substrings that identify a Coffer daemon process. Covers both a
#: run-from-source daemon (``-m coffer.infrastructure.daemon.entry``) and the
#: frozen ``coffer-daemon`` binary.
DAEMON_CMDLINE_MARKERS = ("coffer.infrastructure.daemon.entry", "coffer-daemon")


def pid_is_coffer_daemon(pid: int) -> bool:
    """True iff ``pid`` is a live process whose command line looks like a Coffer
    daemon.

    A recorded pid outlives the daemon that wrote it and can be recycled onto an
    unrelated process, so every decision keyed off a pid in daemon.json — the
    CLI's ``daemon stop`` before it signals, the daemon's own self-eviction
    check before it stands down — has to confirm the pid is still ours. A
    process we cannot inspect is reported as "not a daemon": the callers all
    treat that as "do nothing", which is the safe direction for both.
    """
    try:
        cmdline = psutil.Process(pid).cmdline()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False
    joined = " ".join(cmdline)
    return any(marker in joined for marker in DAEMON_CMDLINE_MARKERS)


@dataclass(frozen=True)
class DaemonInfo:
    version: int
    pid: int
    port: int
    token: str
    started_at: datetime
    binary_path: str


def write(path: Path, info: DaemonInfo) -> None:
    """Atomically write daemon.json with mode 0600.

    The atomicity and the 0600 staging live in
    :func:`~coffer.infrastructure.daemon.atomic_write.write_json_0600`, which
    documents why both matter here: two daemons can race to publish this exact
    path during the detect-or-spawn window.
    """
    write_json_0600(path, {**asdict(info), "started_at": info.started_at.isoformat()})


def read(path: Path) -> DaemonInfo:
    raw = json.loads(path.read_text())
    return DaemonInfo(
        version=raw["version"],
        pid=raw["pid"],
        port=raw["port"],
        token=raw["token"],
        started_at=datetime.fromisoformat(raw["started_at"]),
        binary_path=raw["binary_path"],
    )
