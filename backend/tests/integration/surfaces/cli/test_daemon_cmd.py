"""The `daemon.port` setting's restart hints, the port pre-flight in
`coffer daemon start`, and `coffer daemon service`.

Every test runs under a throwaway ``HOME`` so nothing here can read or write
the developer's real ``~/.coffer``. These deliberately exercise the
no-daemon-running path: that is the state a taken port causes, and — now that
`coffer config`'s `daemon.port` is the only surface for the setting — the
state that key has to remain usable in.

The default port is stood in for by a monkeypatched ``DEFAULT_PORT`` wherever a
test needs to hold it, because the developer's own daemon is usually on the
real 38470 and a test must not have to win it.
"""

from __future__ import annotations

import json
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from coffer.infrastructure.daemon import bootstrap
from coffer.infrastructure.daemon import config as daemon_config
from coffer.infrastructure.daemon import spawn as _spawn
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app

runner = CliRunner()


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway HOME with no daemon of any kind running in it."""
    h = tmp_path / "home"
    (h / ".coffer").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(h))
    return h


def _config(home: Path) -> dict[str, Any]:
    return json.loads((home / ".coffer" / "daemon-config.json").read_text())  # type: ignore[no-any-return]


def test_an_unreadable_config_file_is_reported_where_the_user_can_act(home: Path) -> None:
    """A hand-mangled config is reported where the user can act on it — the
    daemon itself only warns into a log and falls back to the default port."""
    (home / ".coffer" / "daemon-config.json").write_text("{not json")

    res = runner.invoke(app, ["config", "get", "daemon.port"])
    assert res.exit_code == 0, res.output
    assert str(daemon_config.DEFAULT_PORT) in res.output
    assert "could not be read" in res.output


def test_the_port_and_features_ask_the_running_daemon(home: Path) -> None:
    """`coffer config` sets the port while the daemon is down; `daemon port` and
    `settings features` ask the running daemon, as Settings does."""
    for argv in (["daemon", "port", "--help"], ["settings", "features", "--help"]):
        assert runner.invoke(app, argv).exit_code == 0, argv


def _squat_a_port() -> socket.socket:
    """Hold an arbitrary free port the way an unrelated dev server would."""
    squatter = socket.socket()
    squatter.bind(("127.0.0.1", 0))
    squatter.listen(5)
    return squatter


def test_start_refuses_when_the_configured_port_is_held(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pre-flight names the conflict in the terminal instead of letting the
    spawn time out into "check daemon.log"."""
    squatter = _squat_a_port()
    port = squatter.getsockname()[1]
    try:
        assert runner.invoke(app, ["config", "set", "daemon.port", str(port)]).exit_code == 0

        def _must_not_spawn(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("start must not spawn a daemon onto a held port")

        monkeypatch.setattr(_spawn.subprocess, "Popen", _must_not_spawn)

        res = runner.invoke(app, ["daemon", "start"])
    finally:
        squatter.close()

    assert res.exit_code != 0
    assert str(port) in res.output
    assert "coffer config set daemon.port" in res.output
    assert not (home / ".coffer" / "daemon.json").exists()


def test_start_refuses_when_the_default_port_is_held_and_nothing_is_configured(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The common case now, and the one the old pre-flight walked straight past.

    It returned early whenever no port was configured, because a start with no
    configuration used to scan and had no single port to diagnose. A start now
    insists on the default, so the vault where the user has changed nothing is
    exactly the vault this check has to cover — and the diagnosis has to arrive
    before the spawn, not as a boot timeout ten seconds later.
    """
    squatter = _squat_a_port()
    monkeypatch.setattr(daemon_config, "DEFAULT_PORT", squatter.getsockname()[1])
    try:
        assert not (home / ".coffer" / "daemon-config.json").exists()

        def _must_not_spawn(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("start must not spawn a daemon onto a held default port")

        monkeypatch.setattr(_spawn.subprocess, "Popen", _must_not_spawn)

        res = runner.invoke(app, ["daemon", "start"])
    finally:
        squatter.close()

    assert res.exit_code != 0
    assert str(daemon_config.DEFAULT_PORT) in res.output
    # Nothing is configured, so `unset` would change nothing and must not be
    # offered; moving off the default is the way out this user has.
    assert "coffer config set daemon.port" in res.output
    assert "coffer config unset daemon.port" not in res.output
    assert not (home / ".coffer" / "daemon.json").exists()


def test_start_skips_the_pre_flight_under_the_range_override(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A test daemon scans a range of its own, so there is no port to pre-check.

    Without this the pre-flight would diagnose 38470 — a port the start under
    the override was never going to touch — and refuse to spawn every test
    daemon on a developer's machine whose real daemon is up.
    """
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59680")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59689")

    squatter = _squat_a_port()
    monkeypatch.setattr(daemon_config, "DEFAULT_PORT", squatter.getsockname()[1])
    spawned: list[object] = []

    def _record_spawn(*args: Any, **kwargs: Any) -> Any:
        spawned.append(args)
        raise RuntimeError("stop here — the pre-flight let us through, which is the point")

    monkeypatch.setattr(_spawn.subprocess, "Popen", _record_spawn)
    try:
        runner.invoke(app, ["daemon", "start"])
    finally:
        squatter.close()

    assert spawned, "the pre-flight refused a start it has no port to judge"


def _live(monkeypatch: pytest.MonkeyPatch, port: int) -> DaemonInfo:
    """Pretend a daemon is serving on ``port``."""
    info = DaemonInfo(
        version=1,
        pid=4242,
        port=port,
        token="t",
        started_at=datetime.now(tz=UTC),
    )
    monkeypatch.setattr(bootstrap, "live_daemon", lambda: info)
    return info


def test_port_set_writes_the_file_even_with_a_daemon_running(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The file is the only place the setting lives, so the CLI always writes it.

    It used to PUT through the running daemon so the change was audited. That
    route is gone — a setting whose whole job is to be fixable when the daemon
    will not start cannot be served by the daemon — and the CLI writes the file
    in every state instead of only as a fallback.
    """
    _live(monkeypatch, 38470)

    res = runner.invoke(app, ["config", "set", "daemon.port", "8123"])
    assert res.exit_code == 0, res.output
    assert _config(home)["port"] == 8123
    # The daemon owns its bound socket and cannot move, so the user is told
    # the change is still owed a restart.
    assert "38470" in res.output
    assert "coffer daemon restart" in res.output


def test_port_set_to_the_port_already_served_asks_for_no_restart(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing changes for this process, so nothing is owed.

    Saying "restart" here would be false, and a restart hint the user learns to
    disregard is worse than none at all.
    """
    _live(monkeypatch, 8123)

    res = runner.invoke(app, ["config", "set", "daemon.port", "8123"])
    assert res.exit_code == 0, res.output
    assert _config(home)["port"] == 8123
    assert "coffer daemon restart" not in res.output


def test_port_clear_with_a_daemon_on_the_default_asks_for_no_restart(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Clearing returns the daemon to its default port — where it already is.

    This is the case the old wording got wrong: it compared "is a port
    configured?" rather than "will the next start bind what this one did", so
    clearing always read as a no-op even when it moved the daemon.
    """
    assert runner.invoke(app, ["config", "set", "daemon.port", "8123"]).exit_code == 0
    _live(monkeypatch, daemon_config.DEFAULT_PORT)

    res = runner.invoke(app, ["config", "unset", "daemon.port"])
    assert res.exit_code == 0, res.output
    assert _config(home)["port"] is None
    assert "coffer daemon restart" not in res.output


def test_port_clear_away_from_a_daemon_on_a_chosen_port_asks_for_a_restart(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mirror image: the running daemon is on the port being cleared, so
    the next start moves it back to the default and the user must be told."""
    assert runner.invoke(app, ["config", "set", "daemon.port", "8123"]).exit_code == 0
    _live(monkeypatch, 8123)

    res = runner.invoke(app, ["config", "unset", "daemon.port"])
    assert res.exit_code == 0, res.output
    assert _config(home)["port"] is None
    assert "coffer daemon restart" in res.output


def _publish(home: Path, pid: int) -> Path:
    path = home / ".coffer" / "daemon.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    from coffer.infrastructure.daemon.pid_lock import write

    write(
        path,
        DaemonInfo(
            version=1,
            pid=pid,
            port=1,
            token="t",
            started_at=datetime.now(tz=UTC),
        ),
    )
    return path


@pytest.mark.acceptance(spec="daemon", scenario="a restart replaces a daemon that does not answer")
def test_restart_kills_a_daemon_that_does_not_exit_and_starts_another(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from coffer.surfaces.cli import daemon_cmd

    path = _publish(home, 4242)
    forced: list[int] = []
    started: list[bool] = []
    monkeypatch.setattr(daemon_cmd, "pid_is_coffer_daemon", lambda _pid: True)

    def _force(pid: int) -> str:
        forced.append(pid)
        return "killed"

    monkeypatch.setattr(daemon_cmd, "stop_daemon_process", _force)
    monkeypatch.setattr(daemon_cmd, "_start_daemon", lambda: started.append(True))

    res = runner.invoke(app, ["daemon", "restart"])

    assert res.exit_code == 0, res.output
    assert forced == [4242]
    assert "was killed" in res.output
    assert not path.exists(), "the killed daemon's discovery file is removed"
    assert started == [True]


def test_stop_reports_a_daemon_that_does_not_exit_and_points_at_restart(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`stop` never kills: past the grace it says so and names `restart`."""
    from coffer.surfaces.cli import daemon_cmd

    _publish(home, 4242)
    signalled: list[int] = []
    monkeypatch.setattr(daemon_cmd, "pid_is_coffer_daemon", lambda _pid: True)
    monkeypatch.setattr(daemon_cmd.os, "kill", lambda pid, _sig: signalled.append(pid))
    monkeypatch.setattr(daemon_cmd, "_wait_for_daemon_json_gone", lambda *_a, **_k: False)
    monkeypatch.setattr(
        daemon_cmd, "stop_daemon_process", lambda _pid: pytest.fail("stop must not force")
    )

    res = runner.invoke(app, ["daemon", "stop"])

    assert res.exit_code == 1
    assert signalled == [4242]
    assert "coffer daemon restart" in res.output
