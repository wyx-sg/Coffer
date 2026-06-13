"""Integration tests for the ADR-006 spawn-lock: a flock serialises
probe+bind+write+**announce-ready** so two near-simultaneous auto-spawns can't
both bind and clobber daemon.json (orphaning the loser's daemon).

The lock is held from before the liveness probe until the freshly-spawned
daemon is actually serving HTTP — not merely until daemon.json is written.
``acquire_or_existing`` therefore hands the caller a ``release`` callable that
the daemon entrypoint invokes only once uvicorn is listening, so a racing spawn
that wakes up mid-boot either blocks on the still-held lock or sees a
fully-serving daemon — never a half-bound one.

These drive real temp files + a real ``fcntl`` lock + a real bound socket (no
mocks of the lock or the file) so the serialisation guarantee is pinned where
the real OS lock lives.
"""

from __future__ import annotations

import socket
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

from coffer.infrastructure.daemon import bootstrap
from coffer.infrastructure.daemon.pid_lock import DaemonInfo, read, write

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="fcntl flock is POSIX-only")


def _setup_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59200")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59299")
    return home


def _lock_is_free() -> bool:
    """True iff the spawn lock can be taken non-blocking from a fresh fd."""
    import fcntl

    with open(bootstrap._spawn_lock_path()) as probe:
        try:
            fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        fcntl.flock(probe.fileno(), fcntl.LOCK_UN)
        return True


def test_acquire_or_existing_binds_when_no_daemon_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no live daemon, acquire_or_existing() binds a port, writes
    daemon.json recording THIS pid, and hands back the held socket plus a
    release callable for the spawn lock."""
    home = _setup_home(tmp_path, monkeypatch)

    info, sock, release = bootstrap.acquire_or_existing()
    assert sock is not None, "must return the held socket when it bound a port"
    try:
        import os

        assert info.pid == os.getpid()
        daemon_json = home / ".coffer" / "daemon.json"
        assert daemon_json.exists()
        assert sock.getsockname()[1] == info.port
    finally:
        release()
        sock.close()


def test_acquire_or_existing_returns_existing_without_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When a daemon is already live, acquire_or_existing() must NOT bind a
    second port; it returns the existing info and a None socket, releases the
    lock itself, and leaves the existing daemon.json untouched."""
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

    info, sock, release = bootstrap.acquire_or_existing()
    assert sock is None
    assert info.pid == 4242
    assert info.port == 59250
    # The early-exit path released the lock itself; calling the returned
    # release again is a harmless no-op.
    release()
    assert _lock_is_free()


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


def test_acquire_or_existing_holds_lock_until_release_is_called(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bind path keeps the spawn lock held AFTER returning — it is released
    only when the caller invokes the returned callable (which the daemon
    entrypoint does once uvicorn is actually serving). This is the fix for the
    boot window: the lock no longer drops the instant daemon.json is written."""
    _setup_home(tmp_path, monkeypatch)

    _info, sock, release = bootstrap.acquire_or_existing()
    try:
        assert sock is not None
        # daemon.json is already written, yet the lock is STILL held — a racing
        # spawn cannot proceed past the probe during this window.
        assert not _lock_is_free(), "lock must stay held until the daemon is serving"
    finally:
        release()
        sock.close()

    assert _lock_is_free(), "release() must free the lock for the next spawn"


def test_live_daemon_is_none_for_a_bound_but_not_serving_socket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A port that is merely bound (no HTTP server accepting on it yet) is NOT
    a live daemon: live_daemon() probes /daemon/status and must return None.

    This is the real condition the spawn lock must bridge — daemon.json can
    point at a port whose owner has not started serving HTTP, and treating that
    as "live" (the old file-existence shortcut) is exactly what masked the boot
    window. Here we drive a real bound-but-not-serving socket and assert the
    truthful answer.
    """
    home = _setup_home(tmp_path, monkeypatch)

    held = socket.socket()
    held.bind(("127.0.0.1", 0))  # bound, never listen()/serve — like mid-boot
    bound_port = held.getsockname()[1]
    try:
        write(
            home / ".coffer" / "daemon.json",
            DaemonInfo(
                version=1,
                pid=4242,
                port=bound_port,
                token="t",
                started_at=datetime.now(tz=UTC),
                binary_path="/fake/coffer-daemon",
            ),
        )
        assert bootstrap.live_daemon() is None
    finally:
        held.close()


def test_concurrent_acquire_blocks_racer_until_first_is_serving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two threads race acquire_or_existing(). The lock is released by the
    winner only once it is *serving* (modelled by a flag, NOT by daemon.json
    existing). The loser therefore blocks until then, observes the live daemon,
    and does NOT bind a second port. End state: exactly one bound socket, and
    daemon.json's port matches it.

    Liveness here is "the daemon is serving HTTP", which is what a real
    auto-spawn's /daemon/status probe checks — deliberately not "daemon.json is
    present", which would falsely report a half-bound daemon as live and hide
    the very window under test.
    """
    home = _setup_home(tmp_path, monkeypatch)
    daemon_json = home / ".coffer" / "daemon.json"
    serving = threading.Event()

    def _fake_live() -> DaemonInfo | None:
        # Live ONLY once the winner has announced it is serving — mirrors the
        # real /daemon/status probe, which fails on a bound-but-not-serving port.
        if serving.is_set() and daemon_json.exists():
            return read(daemon_json)
        return None

    monkeypatch.setattr(bootstrap, "live_daemon", _fake_live)

    bound: list[socket.socket] = []
    barrier = threading.Barrier(2)
    lock = threading.Lock()

    def _worker() -> None:
        barrier.wait()
        _info, sock, release = bootstrap.acquire_or_existing()
        if sock is not None:
            with lock:
                bound.append(sock)
            # Model the daemon reaching "serving" before it drops the spawn
            # lock: announce liveness, THEN release — the order the entrypoint
            # enforces by releasing only at uvicorn Server.started.
            serving.set()
            release()
        else:
            release()

    t1 = threading.Thread(target=_worker)
    t2 = threading.Thread(target=_worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    try:
        assert len(bound) == 1, "exactly one thread should have bound a port"
        recorded = read(daemon_json)
        assert recorded.port == bound[0].getsockname()[1]
    finally:
        for s in bound:
            s.close()
