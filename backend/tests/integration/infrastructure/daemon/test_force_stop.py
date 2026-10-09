"""Forcing out a wedged daemon on an explicit restart (spec daemon "Force out a
wedged daemon on an explicit restart"), against real child processes."""

from __future__ import annotations

import subprocess
import sys
import time

import pytest

from coffer.infrastructure.daemon import force_stop

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")

_IGNORES_TERM = (
    "import signal, sys, time\n"
    "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
    "sys.stdout.write('ready\\n'); sys.stdout.flush()\n"
    "time.sleep(60)\n"
)
_EXITS_ON_TERM = (
    "import sys, time\nsys.stdout.write('ready\\n'); sys.stdout.flush()\ntime.sleep(60)\n"
)


def _start(code: str) -> subprocess.Popen[str]:
    proc = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    assert proc.stdout is not None
    assert proc.stdout.readline().strip() == "ready"
    return proc


def _reaped(proc: subprocess.Popen[str]) -> bool:
    """Reap our own child so it does not linger as a zombie the check counts."""
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        return False
    return True


@pytest.mark.acceptance(spec="daemon", scenario="a restart replaces a daemon that does not answer")
def test_a_daemon_that_ignores_the_stop_signal_is_killed_after_the_grace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proc = _start(_IGNORES_TERM)
    procs = {proc.pid: proc}
    monkeypatch.setattr(force_stop, "serves_our_vault", lambda _pid: True)
    monkeypatch.setattr(force_stop, "process_is_gone", lambda pid: _poll_gone(pid, procs))
    try:
        outcome = force_stop.stop_daemon_process(proc.pid, grace=0.5)
        assert outcome == "killed"
        # psutil may reap our child first, so its exit status is not ours to read.
        assert _reaped(proc)
    finally:
        if proc.poll() is None:
            proc.kill()


def test_a_daemon_that_exits_on_the_signal_is_stopped_not_killed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proc = _start(_EXITS_ON_TERM)
    procs = {proc.pid: proc}
    monkeypatch.setattr(force_stop, "serves_our_vault", lambda _pid: True)
    monkeypatch.setattr(force_stop, "process_is_gone", lambda pid: _poll_gone(pid, procs))
    try:
        assert force_stop.stop_daemon_process(proc.pid, grace=5.0) == "stopped"
        assert proc.returncode == -15
    finally:
        if proc.poll() is None:
            proc.kill()


@pytest.mark.acceptance(
    spec="daemon", scenario="a restart never kills a process that is not this vault's daemon"
)
def test_a_process_that_is_not_this_vaults_daemon_is_never_signalled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(force_stop, "serves_our_vault", lambda _pid: False)
    proc = _start(_EXITS_ON_TERM)
    try:
        assert force_stop.stop_daemon_process(proc.pid, grace=0.1) == "not_ours"
        time.sleep(0.2)
        assert proc.poll() is None, "a stranger must not be signalled"
    finally:
        proc.kill()
        proc.wait()


def test_a_pid_that_is_gone_is_reported_gone() -> None:
    assert force_stop.stop_daemon_process(2**22 + 12345) == "gone"


def _poll_gone(pid: int, procs: dict[int, subprocess.Popen[str]]) -> bool:
    """Our test children turn into zombies until we reap them; poll() reaps."""
    proc = procs.get(pid)
    if proc is not None:
        return proc.poll() is not None
    return True


def test_the_process_forcing_a_daemon_out_is_spared_when_it_descends_from_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A restart's successor was spawned by the daemon it replaces, so it sits
    in that daemon's tree; the kill must not take the successor with it."""
    import os

    killed: list[int] = []

    class _Proc:
        def __init__(self, pid: int, children: list[_Proc] | None = None) -> None:
            self.pid = pid
            self._children = children or []

        def children(self, recursive: bool = False) -> list[_Proc]:
            return self._children

        def kill(self) -> None:
            killed.append(self.pid)

    us = _Proc(os.getpid())
    sibling = _Proc(2**22 + 1)
    wedged = _Proc(2**22 + 2, [us, sibling])
    monkeypatch.setattr(force_stop.psutil, "wait_procs", lambda procs, timeout: ([], []))

    force_stop._kill_tree_sparing_us(wedged)  # type: ignore[arg-type]

    assert os.getpid() not in killed
    assert sorted(killed) == [sibling.pid, wedged.pid]
