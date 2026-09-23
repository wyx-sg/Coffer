"""The daemon process as its clients see it: spawned detached, published
privately, attached to across builds, and bound to loopback only.

Every test runs under a throwaway ``HOME`` and log directory and binds only
ports from a private range — never the user's real daemon port or ``~/.coffer``.
"""

from __future__ import annotations

import json
import os
import socket
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from coffer.infrastructure.daemon import bootstrap, spawn
from coffer.surfaces.cli import _client as cli_client


def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


# --------------------------------------------------------------------------- #
# Spawn a detached daemon from any surface that needs one                      #
# --------------------------------------------------------------------------- #

_CHILD = r"""
import os, sys
stdin_empty = sys.stdin.read() == ""
print(f"stdin_empty={stdin_empty}", flush=True)
print(f"sid={os.getsid(0)}", flush=True)
sys.stderr.write("refusing to start: port held\n")
sys.stderr.flush()
"""


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX session semantics")
@pytest.mark.acceptance(
    spec="daemon", scenario="a surface that finds no daemon starts one detached"
)
def test_a_spawned_daemon_is_detached_and_writes_to_the_daemon_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolated_home(tmp_path, monkeypatch)
    log_dir = tmp_path / "logs"
    monkeypatch.setenv("COFFER_LOG_DIR", str(log_dir))
    # Stand in for the daemon: a real child process that reports what it was
    # handed, then refuses on stderr the way a daemon with a squatted port does.
    monkeypatch.setattr(spawn, "daemon_spawn_command", lambda: [sys.executable, "-c", _CHILD])
    # An earlier daemon's lines are already in the log; a spawn appends to them.
    log = log_dir / "daemon.log"
    log_dir.mkdir()
    earlier = "an earlier daemon's last line\n"
    log.write_text(earlier)

    proc = spawn.spawn_detached_daemon()
    assert proc.wait(timeout=20) == 0

    text = log.read_text()
    assert text.startswith(earlier), "the spawn must append to daemon.log, not truncate it"
    assert "stdin_empty=True" in text, "the daemon must be given no stdin"
    sid_line = next(line for line in text.splitlines() if line.startswith("sid="))
    child_sid = int(sid_line.removeprefix("sid="))
    assert child_sid == proc.pid, "the daemon must lead a session of its own"
    assert child_sid != os.getsid(0), "the daemon must not share the caller's session"
    assert "refusing to start: port held" in text, "a refusal on stderr must reach daemon.log"


# --------------------------------------------------------------------------- #
# Publish one private discovery file                                           #
# --------------------------------------------------------------------------- #


@pytest.mark.acceptance(
    spec="daemon", scenario="a published discovery file is private and complete"
)
def test_the_discovery_file_is_private_complete_and_read_leniently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _isolated_home(tmp_path, monkeypatch)
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59700")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59749")
    path = home / ".coffer" / "daemon.json"
    assert not path.exists()

    info, sock = bootstrap.acquire()
    try:
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        raw = json.loads(path.read_text())
        assert set(raw) >= {"version", "pid", "port", "token", "started_at", "binary_path"}
        assert raw["version"] == info.version
        assert raw["pid"] == os.getpid()
        assert raw["port"] == sock.getsockname()[1]
        assert raw["token"] == info.token and raw["token"]
        assert datetime.fromisoformat(raw["started_at"]).tzinfo is not None
        assert raw["binary_path"] == sys.executable
    finally:
        sock.close()

    path.write_text("{ not json")
    assert cli_client.discover() is None
    assert bootstrap.live_daemon() is None


# --------------------------------------------------------------------------- #
# Warn on a version mismatch and carry on                                      #
# --------------------------------------------------------------------------- #


def _write_daemon_json(home: Path) -> None:
    path = home / ".coffer" / "daemon.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "pid": 4242,
                "port": 59750,
                "token": "tok",
                "started_at": datetime.now(tz=UTC).isoformat(),
                "binary_path": "/old/coffer-daemon",
            }
        )
    )


@pytest.mark.parametrize(
    ("status", "warned"),
    [
        ({"version": "0.0.0-older-build", "executable": "/old/coffer-daemon"}, True),
        ({"executable": "/old/coffer-daemon"}, False),
        ({"version": 7}, False),
        ({}, False),
        (None, False),
    ],
)
@pytest.mark.acceptance(
    spec="daemon",
    scenario="a daemon that cannot state its version is never called a mismatch",
)
def test_the_cli_warns_on_another_build_and_never_on_missing_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    status: dict[str, Any] | None,
    warned: bool,
) -> None:
    import coffer

    home = _isolated_home(tmp_path, monkeypatch)
    _write_daemon_json(home)
    monkeypatch.setattr(cli_client, "live_daemon", cli_client.discover)
    monkeypatch.setattr(cli_client, "probe_status", lambda _info, timeout: status)

    def _no_spawn() -> None:
        raise AssertionError("a live daemon must be attached to, not replaced")

    monkeypatch.setattr(cli_client, "_spawn_daemon", _no_spawn)

    client, info = cli_client.client_or_exit()
    client.close()

    assert info.port == 59750, "the CLI carries on against the daemon it found"
    err = capsys.readouterr().err
    if warned:
        lines = [line for line in err.splitlines() if "WARNING" in line]
        assert len(lines) == 1, err
        assert "0.0.0-older-build" in lines[0]
        assert coffer.__version__ in lines[0]
        assert "/old/coffer-daemon" in lines[0]
        assert "coffer daemon restart" in lines[0]
    else:
        assert err == ""


# --------------------------------------------------------------------------- #
# Bind every endpoint to loopback only                                         #
# --------------------------------------------------------------------------- #


class _StopBeforeServingError(Exception):
    pass


@pytest.mark.acceptance(spec="daemon", scenario="the daemon listens on loopback only")
def test_the_daemon_listens_on_loopback_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import uvicorn

    from coffer.infrastructure.daemon import entry

    _isolated_home(tmp_path, monkeypatch)
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59760")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59799")

    info, sock = bootstrap.acquire()
    captured: dict[str, Any] = {}
    real_config = uvicorn.Config

    def _capture_config(app: Any, **kwargs: Any) -> uvicorn.Config:
        captured["app"] = app
        captured["kwargs"] = kwargs
        return real_config(app, **kwargs)

    def _stop(_config: uvicorn.Config) -> None:
        raise _StopBeforeServingError

    monkeypatch.setattr(entry.uvicorn, "Config", _capture_config)
    monkeypatch.setattr(entry.uvicorn, "Server", _stop)
    bound_fd = sock.fileno()
    try:
        host, port = sock.getsockname()
        assert sock.family == socket.AF_INET
        assert host == "127.0.0.1"
        assert port == info.port

        with pytest.raises(_StopBeforeServingError):
            entry._run_server(sock, on_started=lambda: None)
    finally:
        sock.close()

    kwargs = captured["kwargs"]
    assert kwargs["fd"] == bound_fd
    assert "host" not in kwargs and "port" not in kwargs and "uds" not in kwargs
    # The one app on that socket serves the management API and /mcp alike.
    assert captured["app"] == "coffer.main:app"
    from coffer.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/mcp" in paths or any(p.startswith("/mcp") for p in paths)
    assert any(p.startswith("/api/v1/") for p in paths)
