"""Integration tests for the ADR-006 spawn-lock: a flock serialises
probe+bind+write so two near-simultaneous auto-spawns can't both bind and
clobber daemon.json (orphaning the loser's daemon).

These drive real temp files + a real ``fcntl`` lock (no mocks) so the
serialisation guarantee is pinned where the real OS lock lives.
"""

from __future__ import annotations

import socket
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from coffer.infrastructure.daemon import bootstrap
from coffer.infrastructure.daemon.pid_lock import DaemonInfo, write

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="fcntl flock is POSIX-only")


def _setup_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59200")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59299")
    return home


def test_acquire_or_existing_binds_when_no_daemon_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no live daemon, acquire_or_existing() binds a port, writes
    daemon.json recording THIS pid, and hands back the held socket."""
    home = _setup_home(tmp_path, monkeypatch)

    info, sock = bootstrap.acquire_or_existing()
    assert sock is not None, "must return the held socket when it bound a port"
    try:
        import os

        assert info.pid == os.getpid()
        daemon_json = home / ".coffer" / "daemon.json"
        assert daemon_json.exists()
        assert sock.getsockname()[1] == info.port
    finally:
        sock.close()


def test_acquire_or_existing_returns_existing_without_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When a daemon is already live, acquire_or_existing() must NOT bind a
    second port; it returns the existing info and a None socket, and leaves
    the existing daemon.json untouched."""
    home = _setup_home(tmp_path, monkeypatch)
    existing = DaemonInfo(
        version=1,
        pid=4242,
        port=59250,
        token="live-tok",
        started_at=datetime.now(tz=UTC),
        binary_path="/fake/coffer-daemon",
    )
    write(home / ".coffer" / "daemon.json", existing)
    monkeypatch.setattr(bootstrap, "live_daemon", lambda: existing)

    def _no_bind(*_a: object, **_k: object) -> object:
        raise AssertionError("must not bind a second port when one is live")

    monkeypatch.setattr(bootstrap, "bind_free_socket", _no_bind)

    info, sock = bootstrap.acquire_or_existing()
    assert sock is None
    assert info.pid == 4242
    assert info.port == 59250


def test_spawn_lock_serialises_probe_and_bind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The flock held across probe+bind+write blocks a concurrent attempt:
    while one holder owns the lock, a second acquire of the lock with
    non-blocking semantics fails (proving the critical section is guarded by
    a real OS lock, not a check-then-act gap)."""
    import fcntl

    _setup_home(tmp_path, monkeypatch)

    with bootstrap._spawn_lock() as _held_fd:
        # A second independent open + non-blocking flock on the same lockfile
        # must fail because the first holder still owns it.
        lock_path = bootstrap._spawn_lock_path()
        with open(lock_path) as f2, pytest.raises(OSError):
            fcntl.flock(f2.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_concurrent_acquire_or_existing_yields_single_daemon_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two threads racing acquire_or_existing(): the lock serialises them so
    the second sees the first's live daemon (via live_daemon) and does NOT
    bind a second port. End state: exactly one bound socket, and daemon.json's
    port matches that socket."""
    import threading

    home = _setup_home(tmp_path, monkeypatch)
    daemon_json = home / ".coffer" / "daemon.json"

    bound: list[socket.socket] = []
    results: list[tuple[DaemonInfo, socket.socket | None]] = []
    barrier = threading.Barrier(2)

    # Make live_daemon() observe the real daemon.json the first winner writes:
    # a daemon is "live" iff daemon.json exists (we can't run a real server in
    # a thread, so liveness == file present, which is exactly what the lock
    # must make the loser observe).
    def _fake_live() -> DaemonInfo | None:
        from coffer.infrastructure.daemon.pid_lock import read

        if daemon_json.exists():
            return read(daemon_json)
        return None

    monkeypatch.setattr(bootstrap, "live_daemon", _fake_live)

    def _worker() -> None:
        barrier.wait()
        info, sock = bootstrap.acquire_or_existing()
        results.append((info, sock))
        if sock is not None:
            bound.append(sock)

    t1 = threading.Thread(target=_worker)
    t2 = threading.Thread(target=_worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    try:
        assert len(bound) == 1, "exactly one thread should have bound a port"
        from coffer.infrastructure.daemon.pid_lock import read

        recorded = read(daemon_json)
        assert recorded.port == bound[0].getsockname()[1]
    finally:
        for s in bound:
            s.close()
