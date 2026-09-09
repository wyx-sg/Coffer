"""Unit tests for the daemon entry module.

TEST-011 — FR-012 requires the daemon to bind only to 127.0.0.1. Since
CODE-041 the daemon binds the socket itself (via ``bind_free_socket``, which
always binds ``127.0.0.1``) and hands uvicorn the fd, so the loopback
guarantee is structural rather than a uvicorn ``host`` kwarg. These tests pin
that entry serves on a pre-bound socket fd (never a host/port that could be
overridden); the companion integration test ``test_port_alloc`` pins that
``bind_free_socket`` actually binds loopback (asserting the bound address
needs the ``socket`` module, which is banned in the pure unit tier).

They also pin the ADR-006 boot-window fix: the spawn lock is released only via
the ``on_started`` callback, which fires once uvicorn reports it is serving —
not when daemon.json is written.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from coffer.infrastructure.daemon import entry


def _setup_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59700")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59799")


class _FakeSock:
    """Minimal stand-in for the pre-bound socket entry.main hands to uvicorn."""

    def __init__(self, fd: int = 7) -> None:
        self._fd = fd
        self.closed = False

    def fileno(self) -> int:
        return self._fd

    def close(self) -> None:
        self.closed = True


def test_main_serves_prebound_socket_and_releases_lock_via_on_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """entry.main hands the pre-bound socket to _run_server and wires the spawn
    lock's release as the on_started callback — so the lock is freed only once
    the server is serving, then daemon.json is cleaned up on shutdown."""
    _setup_home(tmp_path, monkeypatch)

    from coffer.infrastructure.daemon import bootstrap

    sock = _FakeSock(11)
    released: list[str] = []
    info = object()
    monkeypatch.setattr(
        bootstrap,
        "acquire_or_existing",
        lambda: (info, sock, lambda: released.append("released")),
    )

    captured: dict[str, object] = {}

    def _fake_run_server(s: object, on_started: object) -> None:
        captured["sock"] = s
        captured["released_before_run_server"] = list(released)
        # The server reaches "serving" → entry releases the spawn lock here.
        on_started()  # type: ignore[operator]
        captured["released_during_run_server"] = list(released)

    monkeypatch.setattr(entry, "_run_server", _fake_run_server)
    monkeypatch.setattr(entry, "_install_signal_handlers", lambda: None)

    released_on_shutdown: list[bool] = []
    monkeypatch.setattr(bootstrap, "release", lambda: released_on_shutdown.append(True))

    entry.main()

    assert captured["sock"] is sock, "the pre-bound socket must be served as-is"
    # The lock is NOT yet released when serving begins, but IS released by the
    # on_started callback fired while serving — not earlier (e.g. at the
    # daemon.json write). main's finally calls it again; idempotency makes that
    # safe, so we only assert it became released during _run_server.
    assert captured["released_before_run_server"] == []
    assert captured["released_during_run_server"] == ["released"]
    assert released_on_shutdown == [True], "daemon.json released on shutdown"
    assert sock.closed is True


def test_run_server_builds_loopback_fd_config_and_releases_once_started(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_run_server serves the pre-bound fd (no host/port override path) and
    invokes on_started exactly once the server reports it is serving."""
    captured: dict[str, object] = {}

    class _FakeServer:
        def __init__(self, config: object) -> None:
            captured["config"] = config
            self.started = False

        async def serve(self) -> None:
            self.started = True

    monkeypatch.setattr(entry.uvicorn, "Server", _FakeServer)

    started: list[bool] = []
    entry._run_server(_FakeSock(7), lambda: started.append(True))

    config = captured["config"]
    assert config.fd == 7, "must serve the pre-bound socket fd"
    # Binding is owned by the fd (loopback), never widened by a host override.
    assert config.host in (None, "127.0.0.1")
    assert started == [True], "on_started fires once the server is serving"


def test_run_server_releases_even_if_startup_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the server never reaches 'started' (serve returns/raises during
    startup), on_started must still fire so the spawn lock is never leaked —
    otherwise the next auto-spawn would deadlock on it forever."""

    class _FailingServer:
        def __init__(self, config: object) -> None:
            self.started = False  # never becomes True

        async def serve(self) -> None:
            return  # exits without ever serving

    monkeypatch.setattr(entry.uvicorn, "Server", _FailingServer)

    started: list[bool] = []
    entry._run_server(_FakeSock(7), lambda: started.append(True))
    assert started == [True]


def test_no_host_override_path_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Even with COFFER_HOST=0.0.0.0 set, nothing widens the bind.

    _run_server builds a Config from the pre-bound loopback fd and never reads
    COFFER_HOST, so a stray value cannot move the daemon off loopback.
    """
    monkeypatch.setenv("COFFER_HOST", "0.0.0.0")

    captured: dict[str, object] = {}

    class _FakeServer:
        def __init__(self, config: object) -> None:
            captured["config"] = config
            self.started = True

        async def serve(self) -> None:
            return

    monkeypatch.setattr(entry.uvicorn, "Server", _FakeServer)
    entry._run_server(_FakeSock(9), lambda: None)

    config = captured["config"]
    assert config.fd == 9
    assert config.host in (None, "127.0.0.1")


def test_main_refuses_to_start_when_a_daemon_is_already_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-006: if a daemon is already reachable, entry.main() must exit
    cleanly WITHOUT serving — so a racing auto-spawn can't clobber daemon.json
    and orphan the running daemon."""
    from datetime import UTC, datetime

    from coffer.infrastructure.daemon import bootstrap
    from coffer.infrastructure.daemon.pid_lock import DaemonInfo

    _setup_home(tmp_path, monkeypatch)

    existing = DaemonInfo(
        version=1,
        pid=4242,
        port=59750,
        token="live-tok",
        started_at=datetime.now(tz=UTC),
        binary_path="/fake/coffer-daemon",
    )
    # acquire_or_existing returns (existing, None, no-op release) under the
    # spawn lock when a daemon is already live — entry.main must treat a None
    # socket as "exit".
    monkeypatch.setattr(bootstrap, "acquire_or_existing", lambda: (existing, None, lambda: None))

    ran: list[bool] = []
    monkeypatch.setattr(entry, "_run_server", lambda *a, **k: ran.append(True))
    monkeypatch.setattr(entry, "_install_signal_handlers", lambda: None)

    entry.main()  # must return cleanly

    assert ran == [], "the server must NOT run when a daemon is already live"


def test_raise_fd_soft_limit_lifts_soft_toward_capped_hard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A low inherited soft limit (macOS GUI/launchd gives ~256) is raised to
    the target ceiling when the hard limit allows it."""
    import resource

    monkeypatch.setattr(resource, "getrlimit", lambda _which: (256, 10_000))
    calls: list[tuple[int, tuple[int, int]]] = []
    monkeypatch.setattr(resource, "setrlimit", lambda which, limits: calls.append((which, limits)))

    entry._raise_fd_soft_limit()

    # target = min(hard=10_000, cap=8192) = 8192; hard is left untouched.
    assert calls == [(resource.RLIMIT_NOFILE, (entry._FD_SOFT_LIMIT_TARGET, 10_000))]


def test_raise_fd_soft_limit_never_exceeds_hard(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the hard limit is below the target ceiling, soft is raised only up
    to hard — setrlimit would raise ValueError otherwise."""
    import resource

    monkeypatch.setattr(resource, "getrlimit", lambda _which: (256, 1024))
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(resource, "setrlimit", lambda _which, limits: calls.append(limits))

    entry._raise_fd_soft_limit()

    assert calls == [(1024, 1024)]


def test_raise_fd_soft_limit_noops_when_already_high(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the inherited soft limit already clears the target, don't touch it
    (never lower a generous limit)."""
    import resource

    monkeypatch.setattr(resource, "getrlimit", lambda _which: (9000, 10_000))
    calls: list[object] = []
    monkeypatch.setattr(resource, "setrlimit", lambda _which, limits: calls.append(limits))

    entry._raise_fd_soft_limit()

    assert calls == []


def test_raise_fd_soft_limit_is_best_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing setrlimit must never stop the daemon from booting."""
    import resource

    monkeypatch.setattr(resource, "getrlimit", lambda _which: (256, 10_000))

    def _boom(_which: int, _limits: tuple[int, int]) -> None:
        raise OSError("operation not permitted")

    monkeypatch.setattr(resource, "setrlimit", _boom)

    entry._raise_fd_soft_limit()  # must not raise


def test_main_raises_fd_soft_limit_before_serving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """entry.main lifts the fd soft limit before it starts accepting work, so a
    low inherited RLIMIT_NOFILE can't strangle spawns/accepts at runtime."""
    _setup_home(tmp_path, monkeypatch)

    from coffer.infrastructure.daemon import bootstrap

    order: list[str] = []
    monkeypatch.setattr(entry, "_raise_fd_soft_limit", lambda: order.append("fd"))

    sock = _FakeSock(5)
    monkeypatch.setattr(bootstrap, "acquire_or_existing", lambda: (object(), sock, lambda: None))

    def _fake_run_server(_s: object, on_started: object) -> None:
        order.append("serve")
        on_started()  # type: ignore[operator]

    monkeypatch.setattr(entry, "_run_server", _fake_run_server)
    monkeypatch.setattr(entry, "_install_signal_handlers", lambda: None)
    monkeypatch.setattr(bootstrap, "release", lambda: None)

    entry.main()

    assert order and order[0] == "fd", "fd soft limit must be raised before serving"
    assert "serve" in order


def test_entry_does_not_import_the_knowledge_engine() -> None:
    """entry.py is the frozen daemon entrypoint; importing the knowledge engine
    here would pull sqlite-vec into the daemon layer and break engine
    confinement. vec availability is reported via /daemon/status instead."""
    import pathlib

    src = pathlib.Path(entry.__file__).read_text()
    assert "vec_index" not in src
    assert "--check-vec" not in src
