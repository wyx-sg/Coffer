"""Daemon discovery file (~/.coffer/daemon.json) with restrictive permissions,
plus the pid check that says whether a recorded pid is still a Coffer daemon."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import psutil

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
    """Atomically write daemon.json with mode 0600. Caller owns directory creation policy.

    Uses ``tempfile.mkstemp`` (O_CREAT|O_EXCL, mode 0600) for the staging
    file so it never exists with mode broader than 0600 (the previous
    write_text+chmod pair widened that window depending on the caller's umask
    — CODE-018).

    The staging file gets a UNIQUE per-call name in the target directory.
    Two daemons racing to publish daemon.json (the detect-or-spawn
    window) therefore never collide on a shared ``daemon.json.tmp`` — the old
    fixed-name + O_EXCL form crashed the loser with FileExistsError, or let
    one unlink the other's tmp. The final ``os.replace`` is atomic, so the
    last writer wins cleanly with no partial file ever visible at ``path``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {**asdict(info), "started_at": info.started_at.isoformat()}
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f"{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(payload, indent=2))
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
        raise
    os.replace(str(tmp), str(path))


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
