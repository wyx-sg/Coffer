#!/usr/bin/env python3
"""Run a command while holding the machine-wide integration-test lock.

``python scripts/verify_lock.py -- <command> [args...]``

Several worktrees and sessions share one machine. Two integration runs at once
(each with an xdist worker per core, each test starting daemons and git) do not
add up: they slow each other until time-based tests fail. The second run waits
here for the first to finish instead of competing with it.

The lock is an ``fcntl`` lock on ``$XDG_CACHE_HOME/coffer/verify-integration.lock``
(``~/.cache`` by default), so a run that dies releases it with its process.
``COFFER_VERIFY_LOCK=off`` runs the command without the lock (CI runners are
separate machines). The command's exit code is returned, and SIGINT/SIGTERM are
passed on to it.
"""

from __future__ import annotations

import fcntl
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def lock_path() -> Path:
    cache = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(cache) / "coffer" / "verify-integration.lock"


def _holder(fd: int) -> str:
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        return os.read(fd, 200).decode("utf-8", "replace").strip() or "another run"
    except OSError:
        return "another run"


def acquire(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        started = time.monotonic()
        print(
            f"verify-lock: waiting for {_holder(fd)} to finish its integration tests ({path})",
            file=sys.stderr,
            flush=True,
        )
        fcntl.flock(fd, fcntl.LOCK_EX)
        print(
            f"verify-lock: got the lock after {time.monotonic() - started:.0f}s",
            file=sys.stderr,
            flush=True,
        )
    os.ftruncate(fd, 0)
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, f"pid {os.getpid()} in {os.getcwd()}".encode())
    return fd


def run(command: list[str]) -> int:
    child = subprocess.Popen(command)

    def forward(signum: int, _frame: object) -> None:
        child.send_signal(signum)

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, forward)
    code = child.wait()
    # A child killed by a signal reports -N; a shell reports 128+N.
    return 128 - code if code < 0 else code


def main(argv: list[str]) -> int:
    if "--" not in argv:
        print("usage: verify_lock.py -- <command> [args...]", file=sys.stderr)
        return 2
    command = argv[argv.index("--") + 1 :]
    if not command:
        print("usage: verify_lock.py -- <command> [args...]", file=sys.stderr)
        return 2
    if os.environ.get("COFFER_VERIFY_LOCK", "").lower() == "off":
        return run(command)
    fd = acquire(lock_path())
    try:
        return run(command)
    finally:
        os.close(fd)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
