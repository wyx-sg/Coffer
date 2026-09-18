"""ChildProcess against real subprocesses: spawn records a pidfile, the
termination ladder escalates, and the record is dropped once the child is reaped.

Pidfiles land under ``$HOME/.coffer/upstream-pids``; ``HOME`` is pointed at
``tmp_path`` so nothing touches the real vault.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import psutil
import pytest

from coffer.infrastructure.daemon.child_process import ChildProcess

_SLEEP = [sys.executable, "-c", "import time; time.sleep(30)"]
# Prints once the handler is installed so the test never signals a child that
# has not yet decided to ignore SIGTERM (which would prove nothing).
_IGNORES_SIGTERM = [
    sys.executable,
    "-c",
    "import signal, sys, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
    "sys.stdout.write('ready'); sys.stdout.flush(); time.sleep(30)",
]


@pytest.fixture
def pid_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path / ".coffer" / "upstream-pids"


async def test_spawn_records_pidfile_named_after_child_and_pid(pid_dir: Path) -> None:
    child = await ChildProcess.spawn("unit-child", _SLEEP)
    try:
        assert child.running is True
        assert child.returncode is None
        assert child.pidfile == pid_dir / f"unit-child-{child.pid}.json"
        recorded = json.loads(child.pidfile.read_text())
        assert recorded["pid"] == child.pid
        assert recorded["command_line"] == _SLEEP
        # The record keys the child by the uid it was spawned under
        # (``record_spawn``'s ``server_uid``): a pidfile outlives the daemon
        # that wrote it, so it must not be titled with a label the user can
        # change in between (ADR resource-identity-is-an-immutable-uid). The
        # assertion is the same one as before — the name this child was spawned
        # under is written down — under the key that now carries it.
        assert recorded["server_uid"] == "unit-child"
        # The pid is a live process running exactly the recorded command line —
        # what the startup sweep will compare against.
        assert psutil.Process(child.pid).cmdline() == _SLEEP
    finally:
        await child.terminate(timeout=1.0, kill_timeout=1.0)


async def test_spawn_passes_stdio_pipes_and_env_through(pid_dir: Path) -> None:
    argv = [sys.executable, "-c", "import os, sys; sys.stdout.write(os.environ['COFFER_X'])"]
    child = await ChildProcess.spawn(
        "echo-child", argv, env={"COFFER_X": "marker"}, stdout=asyncio.subprocess.PIPE
    )
    assert child.process.stdout is not None
    out = await child.process.stdout.read()
    assert out == b"marker"
    assert await child.wait() == 0
    assert child.running is False
    await child.terminate()
    assert not child.pidfile.exists()


async def test_terminate_escalates_to_sigkill_when_child_ignores_sigterm(pid_dir: Path) -> None:
    child = await ChildProcess.spawn("stubborn", _IGNORES_SIGTERM, stdout=asyncio.subprocess.PIPE)
    pid = child.pid
    assert child.process.stdout is not None
    assert await asyncio.wait_for(child.process.stdout.readexactly(5), timeout=10) == b"ready"
    assert child.pidfile.exists()

    started = time.monotonic()
    await child.terminate(timeout=0.3, kill_timeout=0.3)
    elapsed = time.monotonic() - started

    assert child.running is False
    assert child.returncode == -9  # SIGKILL, not a SIGTERM exit
    assert 0.3 <= elapsed < 2.0  # waited for SIGTERM, then escalated promptly
    assert not psutil.pid_exists(pid) or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
    assert not child.pidfile.exists()
    assert list(pid_dir.glob("*.json")) == []


async def test_terminate_on_exited_child_drops_pidfile_without_error(pid_dir: Path) -> None:
    child = await ChildProcess.spawn("quick", [sys.executable, "-c", "raise SystemExit(3)"])
    assert await child.wait() == 3
    assert child.returncode == 3
    assert child.pidfile.exists()  # nothing has dropped it yet

    await child.terminate(timeout=0.3, kill_timeout=0.3)
    assert not child.pidfile.exists()
    # Idempotent: a second call finds nothing to do and nothing to unlink.
    await child.terminate(timeout=0.3, kill_timeout=0.3)
    assert child.running is False


async def test_wait_returns_exit_code(pid_dir: Path) -> None:
    child = await ChildProcess.spawn("exit-code", [sys.executable, "-c", "raise SystemExit(7)"])
    assert await child.wait() == 7
    assert child.returncode == 7
    await child.terminate()
