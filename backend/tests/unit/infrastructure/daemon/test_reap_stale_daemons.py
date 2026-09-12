"""Reaping stale sibling daemons on bind (detect-or-spawn follow-on).

A persistent, detached daemon that stops answering the liveness probe (wedged,
mid-crash, or a spawn-race loser) is never terminated by the existing machinery:
``bootstrap.release()`` only guards ``daemon.json``, and ``sweep_orphans`` reaps
only ``~/.coffer/upstream-pids`` (MCP upstreams). So displaced daemons accumulate
across app launches. When a fresh daemon WINS the bind (no other daemon is live),
it reaps any other daemon **serving the same vault**.

The vault half is what these tests mostly pin, because getting it wrong is not a
missed cleanup but a wrong kill: every vault runs a binary called
``coffer-daemon``, so matching the name alone made a release smoke test under a
throwaway ``HOME`` terminate the maintainer's live daemon.

The selection logic is pure and exhaustively tested here; the psutil-driven
``reap_stale_daemons`` is tested with fakes (never killing real processes — in a
source run the daemon executable is ``python``, so a live sweep would target
unrelated interpreters, which is exactly why the real path is frozen-only).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from coffer.infrastructure.daemon import orphan_sweep
from coffer.infrastructure.daemon.orphan_sweep import (
    _select_stale_daemons,
    reap_stale_daemons,
)

OURS = Path("/Users/dev/.coffer")
THEIRS = Path("/tmp/coffer-smoke-XXXX/.coffer")


class _FakeProc:
    def __init__(self, pid: int, exe: str | None, home: str | None = "/Users/dev") -> None:
        self.pid = pid
        self._exe = exe
        self._home = home

    def exe(self) -> str:
        if self._exe is None:
            raise OSError("no exe")
        return self._exe

    def environ(self) -> dict[str, str]:
        if self._home is None:
            raise orphan_sweep.psutil.AccessDenied(self.pid)
        return {"HOME": self._home}


def test_select_reaps_matching_sibling_not_protected() -> None:
    candidates = [(200, "coffer-daemon", OURS)]
    assert _select_stale_daemons(
        candidates, protected={100, 99}, own_exe_basename="coffer-daemon", own_coffer_dir=OURS
    ) == [200]


def test_select_excludes_self_and_ancestors() -> None:
    # 100 = us, 99 = the PyInstaller bootloader parent — both protected.
    candidates = [
        (100, "coffer-daemon", OURS),
        (99, "coffer-daemon", OURS),
        (200, "coffer-daemon", OURS),
    ]
    assert _select_stale_daemons(
        candidates, protected={100, 99}, own_exe_basename="coffer-daemon", own_coffer_dir=OURS
    ) == [200]


def test_select_excludes_different_executables() -> None:
    candidates = [
        (200, "coffer-daemon", OURS),  # sibling → reap
        (201, "python3.12", OURS),  # unrelated interpreter → keep
        (202, "coffer-callback", OURS),  # sibling binary, different exe → keep
        (203, None, OURS),  # unreadable exe → keep
    ]
    assert _select_stale_daemons(
        candidates, protected=set(), own_exe_basename="coffer-daemon", own_coffer_dir=OURS
    ) == [200]


def test_select_spares_a_daemon_serving_another_vault() -> None:
    """The regression: a smoke test / live test daemon under a throwaway HOME
    runs the same binary but owns none of our state. Killing it took down the
    maintainer's real daemon, its daemon.json, its callback child and its
    tunnel."""
    candidates = [
        (200, "coffer-daemon", OURS),  # same vault → reap
        (201, "coffer-daemon", THEIRS),  # another vault → keep
    ]
    assert _select_stale_daemons(
        candidates, protected=set(), own_exe_basename="coffer-daemon", own_coffer_dir=OURS
    ) == [200]


def test_select_spares_a_daemon_whose_vault_cannot_be_read() -> None:
    """ "Not provably ours" has to mean "leave it alone": a wrong kill costs a
    running daemon, a missed one costs a port the next start reports."""
    candidates = [(200, "coffer-daemon", None)]
    assert (
        _select_stale_daemons(
            candidates, protected=set(), own_exe_basename="coffer-daemon", own_coffer_dir=OURS
        )
        == []
    )


def test_select_reaps_nothing_when_our_own_vault_is_unknown() -> None:
    candidates = [(200, "coffer-daemon", OURS), (201, "coffer-daemon", THEIRS)]
    assert (
        _select_stale_daemons(
            candidates, protected=set(), own_exe_basename="coffer-daemon", own_coffer_dir=None
        )
        == []
    )


@pytest.mark.parametrize(
    "home,expected",
    [
        ("/Users/dev", Path("/Users/dev/.coffer")),
        ("/Users/dev/", Path("/Users/dev/.coffer")),
        (None, None),
        ("", None),
    ],
)
def test_coffer_dir_for_normalises_or_refuses(home: str | None, expected: Path | None) -> None:
    assert orphan_sweep._coffer_dir_for(home) == expected


def test_proc_coffer_dir_is_none_when_the_environment_is_unreadable() -> None:
    assert orphan_sweep._proc_coffer_dir(_FakeProc(200, "/A/coffer-daemon", home=None)) is None


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
    monkeypatch.setenv("HOME", "/Users/dev")
    own_pid, boot_pid = 100, 99
    daemon_exe = "/A/Coffer.app/Contents/MacOS/coffer-daemon"
    procs = [
        _FakeProc(own_pid, daemon_exe),  # us
        _FakeProc(boot_pid, daemon_exe),  # bootloader
        _FakeProc(200, daemon_exe),  # STALE, our vault → kill
        _FakeProc(201, "/usr/bin/python3.12"),  # unrelated → keep
        _FakeProc(202, "/A/Coffer.app/Contents/MacOS/coffer-callback"),  # keep
        _FakeProc(203, daemon_exe, home="/tmp/coffer-smoke-XXXX"),  # other vault → keep
    ]
    monkeypatch.setattr(orphan_sweep.psutil, "process_iter", lambda: iter(procs))
    monkeypatch.setattr(orphan_sweep, "_protected_pids", lambda pid: {own_pid, boot_pid})
    killed: list[int] = []
    monkeypatch.setattr(orphan_sweep, "_kill_proc_tree", lambda proc, **kw: killed.append(proc.pid))

    assert reap_stale_daemons() == 1
    assert killed == [200]


def test_reap_does_not_read_the_environment_of_unrelated_processes(monkeypatch) -> None:
    """Only same-executable candidates are asked where their vault is — a
    syscall per process on a machine with hundreds of them is not free, and an
    unrelated process's environment is none of our business."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/A/coffer-daemon", raising=False)
    monkeypatch.setenv("HOME", "/Users/dev")
    asked: list[int] = []

    class _Watched(_FakeProc):
        def environ(self) -> dict[str, str]:
            asked.append(self.pid)
            return super().environ()

    procs = [_Watched(200, "/A/coffer-daemon"), _Watched(201, "/usr/bin/node")]
    monkeypatch.setattr(orphan_sweep.psutil, "process_iter", lambda: iter(procs))
    monkeypatch.setattr(orphan_sweep, "_protected_pids", lambda pid: set())
    monkeypatch.setattr(orphan_sweep, "_kill_proc_tree", lambda proc, **kw: None)

    reap_stale_daemons()
    assert asked == [200]


def test_reap_swallows_kill_failures(monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/A/coffer-daemon", raising=False)
    monkeypatch.setenv("HOME", "/Users/dev")
    monkeypatch.setattr(
        orphan_sweep.psutil, "process_iter", lambda: iter([_FakeProc(200, "/A/coffer-daemon")])
    )
    monkeypatch.setattr(orphan_sweep, "_protected_pids", lambda pid: set())

    def _raise(proc, **kw) -> None:
        raise orphan_sweep.psutil.NoSuchProcess(proc.pid)

    monkeypatch.setattr(orphan_sweep, "_kill_proc_tree", _raise)
    # A process that dies between enumeration and kill must not crash the sweep.
    assert reap_stale_daemons() == 0
