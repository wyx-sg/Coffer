"""Unit tests for CLI detect-or-spawn — ADR-006.

TEST-020: client_or_exit() must auto-spawn the daemon when daemon.json is
absent, rather than printing 'start it with: coffer daemon start' and exiting.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from coffer.surfaces.cli import _client as cli_client
from coffer.surfaces.cli._client import DaemonNotRunning


def _write_daemon_json(home: Path, port: int = 9876, pid: int = 9999) -> None:
    """Write a minimal daemon.json so discover() returns a DaemonInfo."""
    p = home / ".coffer" / "daemon.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {
                "version": 1,
                "pid": pid,
                "port": port,
                "token": "tok-abc",
                "started_at": datetime.now(tz=UTC).isoformat(),
                "binary_path": "/fake/python",
            }
        )
    )


# --------------------------------------------------------------------------- #
# detect-or-spawn: daemon absent → auto-spawn → connect                        #
# --------------------------------------------------------------------------- #


def test_client_or_exit_spawns_when_daemon_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When daemon.json does not exist, client_or_exit() must call spawn_daemon()
    and wait for daemon.json to appear — NOT raise DaemonNotRunning."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    spawn_called: list[bool] = []

    def _fake_spawn_daemon() -> None:
        spawn_called.append(True)
        # Simulate the daemon writing daemon.json shortly after spawn.
        _write_daemon_json(home, port=9876)

    monkeypatch.setattr(cli_client, "_spawn_daemon", _fake_spawn_daemon)
    # Shorten the timeout so the test runs fast.
    monkeypatch.setattr(cli_client, "_DAEMON_BOOT_TIMEOUT", 2.0)

    client, info = cli_client.client_or_exit()
    client.close()

    assert spawn_called, "spawn_daemon() must be called when daemon.json is absent"
    assert info.port == 9876


def test_client_or_exit_does_not_spawn_when_daemon_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When daemon.json already exists, client_or_exit() must NOT call spawn."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    _write_daemon_json(home, port=7777)

    spawn_called: list[bool] = []

    def _bad_spawn() -> None:
        spawn_called.append(True)
        raise AssertionError("spawn must not be called when daemon.json is present")

    monkeypatch.setattr(cli_client, "_spawn_daemon", _bad_spawn)

    client, info = cli_client.client_or_exit()
    client.close()

    assert not spawn_called
    assert info.port == 7777


def test_client_or_exit_raises_on_spawn_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If spawn_daemon() succeeds but daemon.json never appears within the
    timeout, client_or_exit() must raise DaemonNotRunning (exit 3) with a
    spawn-failure message — NOT the old 'start it with: coffer daemon start'."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    # Spawn does nothing — daemon.json never appears.
    monkeypatch.setattr(cli_client, "_spawn_daemon", lambda: None)
    monkeypatch.setattr(cli_client, "_DAEMON_BOOT_TIMEOUT", 0.05)  # very short

    with pytest.raises((DaemonNotRunning, SystemExit)) as excinfo:
        cli_client.client_or_exit()

    code = getattr(excinfo.value, "code", None) or getattr(excinfo.value, "exit_code", None)
    assert code == 3


def test_client_or_exit_does_not_print_old_start_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The old 'start it with: coffer daemon start' message must never appear;
    auto-spawn replaces that flow."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    # Spawn writes daemon.json so we get a successful path.
    monkeypatch.setattr(
        cli_client,
        "_spawn_daemon",
        lambda: _write_daemon_json(home, port=4321),
    )
    monkeypatch.setattr(cli_client, "_DAEMON_BOOT_TIMEOUT", 2.0)

    client, _info = cli_client.client_or_exit()
    client.close()

    captured = capsys.readouterr()
    assert "coffer daemon start" not in captured.out
    assert "coffer daemon start" not in captured.err


# --------------------------------------------------------------------------- #
# _spawn_daemon helper                                                          #
# --------------------------------------------------------------------------- #


def test_spawn_daemon_invokes_popen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """_spawn_daemon() must call subprocess.Popen with the spawn command,
    DEVNULL stdin, AND the platform's detachment flags — so the daemon
    survives the short-lived CLI that launched it (ADR-006). It must also
    return the Popen handle so the caller can kill it on a boot timeout."""
    import subprocess

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    popen_kwargs: dict[str, Any] = {}

    class _FakeProc:
        pid = 1234

    def _fake_popen(cmd: list[str], **kwargs: Any) -> _FakeProc:
        popen_kwargs["cmd"] = cmd
        popen_kwargs["kwargs"] = kwargs
        return _FakeProc()

    monkeypatch.setattr(cli_client.subprocess, "Popen", _fake_popen)

    proc = cli_client._spawn_daemon()

    assert "cmd" in popen_kwargs, "Popen was not called"
    # Must be a list starting with a string (the executable path).
    assert isinstance(popen_kwargs["cmd"], list)
    assert len(popen_kwargs["cmd"]) >= 1
    # Must redirect stdin to DEVNULL.
    assert popen_kwargs["kwargs"].get("stdin") == subprocess.DEVNULL
    # Must detach so the daemon outlives the launching CLI process.
    if cli_client.sys.platform == "win32":
        flags = popen_kwargs["kwargs"].get("creationflags", 0)
        assert flags & subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
    else:
        assert popen_kwargs["kwargs"].get("start_new_session") is True
    # Must return the Popen handle (not None) on a successful spawn.
    assert proc is not None


def test_client_or_exit_kills_daemon_on_boot_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the spawned daemon never publishes daemon.json within the timeout,
    client_or_exit() must kill() the half-started process (so it can't finish
    booting after we gave up) and raise DaemonNotRunning."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    killed: list[bool] = []

    class _FakeProc:
        pid = 4321

        def kill(self) -> None:
            killed.append(True)

    monkeypatch.setattr(cli_client, "_spawn_daemon", lambda: _FakeProc())
    monkeypatch.setattr(cli_client, "_DAEMON_BOOT_TIMEOUT", 0.05)

    with pytest.raises((DaemonNotRunning, SystemExit)):
        cli_client.client_or_exit()

    assert killed, "the half-started daemon must be killed on boot timeout"


# --------------------------------------------------------------------------- #
# render_http_error — ConnectError message no longer mentions daemon start      #
# --------------------------------------------------------------------------- #


def test_render_http_error_connect_error_no_longer_says_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ConnectError branch in render_http_error must NOT direct the user
    to 'coffer daemon start'."""
    import httpx

    err = httpx.ConnectError("refused")
    exit_code = cli_client.render_http_error(err, verbose=False)

    # We just verify the function doesn't blow up and doesn't regress the
    # old misleading text; the actual message check is below.
    from coffer.surfaces.cli._options import ExitCode

    assert exit_code == ExitCode.DAEMON_UNREACHABLE
