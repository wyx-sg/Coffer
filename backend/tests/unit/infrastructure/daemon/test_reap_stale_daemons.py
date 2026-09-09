"""Reaping stale sibling daemons on bind (ADR-006 follow-on).

A persistent, detached daemon that stops answering the liveness probe (wedged,
mid-crash, or a spawn-race loser) is never terminated by the existing machinery:
``bootstrap.release()`` only guards ``daemon.json``, and ``sweep_orphans`` reaps
only ``~/.coffer/upstream-pids`` (MCP upstreams). So displaced daemons accumulate
across app launches. When a fresh daemon WINS the bind (no other daemon is live),
it reaps any other process running the same daemon executable.

The selection logic is pure and exhaustively tested here; the psutil-driven
``reap_stale_daemons`` is tested with fakes (never killing real processes — in a
source run the daemon executable is ``python``, so a live sweep would target
unrelated interpreters, which is exactly why the real path is frozen-only).
"""

from __future__ import annotations

import sys

from coffer.infrastructure.daemon import orphan_sweep
from coffer.infrastructure.daemon.orphan_sweep import (
    _select_stale_daemons,
    reap_stale_daemons,
)


class _FakeProc:
    def __init__(self, pid: int, exe: str | None) -> None:
        self.pid = pid
        self._exe = exe

    def exe(self) -> str:
        if self._exe is None:
            raise OSError("no exe")
        return self._exe


def test_select_reaps_matching_sibling_not_protected() -> None:
    candidates = [(200, "coffer-daemon")]
    assert _select_stale_daemons(
        candidates, protected={100, 99}, own_exe_basename="coffer-daemon"
    ) == [200]


def test_select_excludes_self_and_ancestors() -> None:
    # 100 = us, 99 = the PyInstaller bootloader parent — both protected.
    candidates = [(100, "coffer-daemon"), (99, "coffer-daemon"), (200, "coffer-daemon")]
    assert _select_stale_daemons(
        candidates, protected={100, 99}, own_exe_basename="coffer-daemon"
    ) == [200]


def test_select_excludes_different_executables() -> None:
    candidates = [
        (200, "coffer-daemon"),  # sibling → reap
        (201, "python3.12"),  # unrelated interpreter → keep
        (202, "coffer-callback"),  # sibling binary, different exe → keep
        (203, None),  # unreadable exe → keep
    ]
    assert _select_stale_daemons(candidates, protected=set(), own_exe_basename="coffer-daemon") == [
        200
    ]


def test_reap_is_noop_when_not_frozen(monkeypatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)

    # Must not even enumerate processes when running from source.
    def _boom() -> object:
        raise AssertionError("process_iter must not be called from a source run")

    monkeypatch.setattr(orphan_sweep.psutil, "process_iter", _boom)
    assert reap_stale_daemons() == 0


def test_reap_kills_only_matching_siblings(monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        sys, "executable", "/A/Coffer.app/Contents/MacOS/coffer-daemon", raising=False
    )
    own_pid, boot_pid = 100, 99
    procs = [
        _FakeProc(own_pid, "/A/Coffer.app/Contents/MacOS/coffer-daemon"),  # us
        _FakeProc(boot_pid, "/A/Coffer.app/Contents/MacOS/coffer-daemon"),  # bootloader
        _FakeProc(200, "/A/Coffer.app/Contents/MacOS/coffer-daemon"),  # STALE → kill
        _FakeProc(201, "/usr/bin/python3.12"),  # unrelated → keep
        _FakeProc(202, "/A/Coffer.app/Contents/MacOS/coffer-callback"),  # keep
    ]
    monkeypatch.setattr(orphan_sweep.psutil, "process_iter", lambda: iter(procs))
    monkeypatch.setattr(orphan_sweep, "_protected_pids", lambda pid: {own_pid, boot_pid})
    killed: list[int] = []
    monkeypatch.setattr(orphan_sweep, "_kill_proc_tree", lambda proc, **kw: killed.append(proc.pid))

    assert reap_stale_daemons() == 1
    assert killed == [200]


def test_reap_swallows_kill_failures(monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/A/coffer-daemon", raising=False)
    monkeypatch.setattr(
        orphan_sweep.psutil, "process_iter", lambda: iter([_FakeProc(200, "/A/coffer-daemon")])
    )
    monkeypatch.setattr(orphan_sweep, "_protected_pids", lambda pid: set())

    def _raise(proc, **kw) -> None:
        raise orphan_sweep.psutil.NoSuchProcess(proc.pid)

    monkeypatch.setattr(orphan_sweep, "_kill_proc_tree", _raise)
    # A process that dies between enumeration and kill must not crash the sweep.
    assert reap_stale_daemons() == 0
