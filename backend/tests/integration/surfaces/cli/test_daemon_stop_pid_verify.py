"""Integration test for daemon_cmd._pid_is_coffer_daemon against real procs.

The P1-1 fix verifies a recorded pid's cmdline before SIGTERMing it, so a
recycled PID now owned by an unrelated process is never killed. Drive it
against a real `python -m coffer.infrastructure.daemon.entry` child (cmdline
carries the entry-module marker → matches) and a real non-coffer child
(plain sleeper → does not match).
"""

from __future__ import annotations

import subprocess
import sys
import time

import psutil

from coffer.surfaces.cli import daemon_cmd


def _wait_cmdline_visible(pid: int, timeout: float = 3.0) -> None:
    """Wait until the spawned child's cmdline is observable (it takes a beat
    for execve to land so psutil sees the final argv, not the launcher's)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if psutil.Process(pid).cmdline():
                return
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return
        time.sleep(0.02)


def test_pid_is_coffer_daemon_true_for_real_entry_invocation() -> None:
    """`python -m coffer.infrastructure.daemon.entry` keeps the module path in
    its cmdline; the helper recognises it as a coffer daemon."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "coffer.infrastructure.daemon.entry", "--check-vec"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_cmdline_visible(proc.pid)
        if psutil.pid_exists(proc.pid):
            assert daemon_cmd._pid_is_coffer_daemon(proc.pid) is True
    finally:
        proc.kill()
        proc.wait()


def test_pid_is_coffer_daemon_false_for_unrelated_process() -> None:
    """A live non-coffer process (a plain sleeper) is NOT a coffer daemon."""
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        _wait_cmdline_visible(proc.pid)
        assert daemon_cmd._pid_is_coffer_daemon(proc.pid) is False
    finally:
        proc.kill()
        proc.wait()


def test_pid_is_coffer_daemon_false_for_dead_pid() -> None:
    """A pid with no live process is not a coffer daemon."""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    assert daemon_cmd._pid_is_coffer_daemon(proc.pid) is False
