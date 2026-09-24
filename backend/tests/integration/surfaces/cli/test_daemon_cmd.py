"""`coffer daemon port` + the port pre-flight in `coffer daemon start`.

Every test runs under a throwaway ``HOME`` so nothing here can read or write
the developer's real ``~/.coffer``. These deliberately exercise the
no-daemon-running path: that is the state a taken port causes, and — now that
this CLI group is the only surface for the setting — the state the whole
sub-group has to remain usable in.

The default port is stood in for by a monkeypatched ``DEFAULT_PORT`` wherever a
test needs to hold it, because the developer's own daemon is usually on the
real 8000 and a test must not have to win it.
"""

from __future__ import annotations

import json
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from coffer.infrastructure.daemon import config as daemon_config
from coffer.infrastructure.daemon import spawn as _spawn
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli import daemon_port_cmd
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


def test_port_set_then_show_round_trips_without_a_daemon(home: Path) -> None:
    res = runner.invoke(app, ["daemon", "port", "set", "8123"])
    assert res.exit_code == 0, res.output
    assert "8123" in res.output
    assert "daemon not running" in res.output
    assert _config(home)["port"] == 8123

    res = runner.invoke(app, ["daemon", "port", "show", "--json"])
    assert res.exit_code == 0, res.output
    payload = json.loads(res.stdout)
    assert payload == {
        "configured_port": 8123,
        "effective_port": None,
        "daemon_running": False,
        "config_readable": True,
    }

    res = runner.invoke(app, ["daemon", "port", "show"])
    assert res.exit_code == 0, res.output
    assert "8123" in res.output
    assert "not running" in res.output


def test_port_clear_returns_to_the_default(home: Path) -> None:
    """Clearing names the port it goes back to.

    "cleared" on its own used to mean "automatic", and saying only that now
    would leave the user with no idea which address to open.
    """
    assert runner.invoke(app, ["daemon", "port", "set", "8123"]).exit_code == 0

    res = runner.invoke(app, ["daemon", "port", "clear"])
    assert res.exit_code == 0, res.output
    assert str(daemon_config.DEFAULT_PORT) in res.output
    assert "automatic" not in res.output
    assert _config(home)["port"] is None

    payload = json.loads(runner.invoke(app, ["daemon", "port", "show", "--json"]).stdout)
    assert payload["configured_port"] is None


def test_port_show_reports_the_default_when_nothing_is_configured(home: Path) -> None:
    """An unconfigured vault has an address, and `show` is where it is read."""
    res = runner.invoke(app, ["daemon", "port", "show"])
    assert res.exit_code == 0, res.output
    assert f"default ({daemon_config.DEFAULT_PORT})" in res.output
    assert "automatic" not in res.output
    assert not (home / ".coffer" / "daemon-config.json").exists()


def test_port_show_flags_a_config_file_it_cannot_read(home: Path) -> None:
    """A hand-mangled config is reported where the user can act on it — the
    daemon itself only warns into a log and falls back to the default port."""
    (home / ".coffer" / "daemon-config.json").write_text("{not json")

    res = runner.invoke(app, ["daemon", "port", "show"])
    assert res.exit_code == 0, res.output
    assert "could not be read" in res.output
    assert json.loads(runner.invoke(app, ["daemon", "port", "show", "--json"]).stdout) == {
        "configured_port": None,
        "effective_port": None,
        "daemon_running": False,
        "config_readable": False,
    }


@pytest.mark.parametrize("bad", ["80", "70000", "0"])
def test_port_set_rejects_an_unbindable_port_and_writes_nothing(home: Path, bad: str) -> None:
    res = runner.invoke(app, ["daemon", "port", "set", bad])
    assert res.exit_code != 0
    assert "1024" in res.output and "65535" in res.output
    assert not (home / ".coffer" / "daemon-config.json").exists()


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
        assert runner.invoke(app, ["daemon", "port", "set", str(port)]).exit_code == 0

        def _must_not_spawn(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("start must not spawn a daemon onto a held port")

        monkeypatch.setattr(_spawn.subprocess, "Popen", _must_not_spawn)

        res = runner.invoke(app, ["daemon", "start"])
    finally:
        squatter.close()

    assert res.exit_code != 0
    assert str(port) in res.output
    assert "coffer daemon port set" in res.output
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
    # Nothing is configured, so `clear` would change nothing and must not be
    # offered; moving off the default is the way out this user has.
    assert "coffer daemon port set" in res.output
    assert "coffer daemon port clear" not in res.output
    assert not (home / ".coffer" / "daemon.json").exists()


def test_start_skips_the_pre_flight_under_the_range_override(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A test daemon scans a range of its own, so there is no port to pre-check.

    Without this the pre-flight would diagnose 8000 — a port the start under
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
        binary_path="/test",
    )
    monkeypatch.setattr(daemon_port_cmd.bootstrap, "live_daemon", lambda: info)
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
    _live(monkeypatch, 8000)

    res = runner.invoke(app, ["daemon", "port", "set", "8123"])
    assert res.exit_code == 0, res.output
    assert _config(home)["port"] == 8123
    # The daemon owns its bound socket and cannot move, so the user is told
    # the change is still owed a restart.
    assert "8000" in res.output
    assert "coffer daemon restart" in res.output


def test_port_set_to_the_port_already_served_asks_for_no_restart(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing changes for this process, so nothing is owed.

    Saying "restart" here would be false, and a restart hint the user learns to
    disregard is worse than none at all.
    """
    _live(monkeypatch, 8123)

    res = runner.invoke(app, ["daemon", "port", "set", "8123"])
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
    assert runner.invoke(app, ["daemon", "port", "set", "8123"]).exit_code == 0
    _live(monkeypatch, daemon_config.DEFAULT_PORT)

    res = runner.invoke(app, ["daemon", "port", "clear"])
    assert res.exit_code == 0, res.output
    assert _config(home)["port"] is None
    assert "coffer daemon restart" not in res.output


def test_port_clear_away_from_a_daemon_on_a_chosen_port_asks_for_a_restart(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mirror image: the running daemon is on the port being cleared, so
    the next start moves it back to the default and the user must be told."""
    assert runner.invoke(app, ["daemon", "port", "set", "8123"]).exit_code == 0
    _live(monkeypatch, 8123)

    res = runner.invoke(app, ["daemon", "port", "clear"])
    assert res.exit_code == 0, res.output
    assert _config(home)["port"] is None
    assert "coffer daemon restart" in res.output


def test_port_show_reports_the_port_the_daemon_is_actually_on(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert runner.invoke(app, ["daemon", "port", "set", "8123"]).exit_code == 0
    _live(monkeypatch, 8000)

    payload = json.loads(runner.invoke(app, ["daemon", "port", "show", "--json"]).stdout)
    assert payload["configured_port"] == 8123
    assert payload["effective_port"] == 8000
    assert payload["daemon_running"] is True

    res = runner.invoke(app, ["daemon", "port", "show"])
    assert "running on 8000" in res.output
    assert "coffer daemon restart" in res.output


@pytest.mark.acceptance(
    spec="daemon", scenario="the command line changes residency with no daemon running"
)
def test_the_command_line_changes_residency_with_no_daemon_running(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`service` writes straight to launchd with no daemon and no database,
    and there is no idle window left to set. launchd is faked: nothing here
    may touch the real one."""
    from coffer.infrastructure.daemon import login_service

    installed = {"value": False}
    plist = home / "Library" / "LaunchAgents" / "fake.plist"

    def _install() -> Path:
        installed["value"] = True
        return plist

    def _uninstall() -> bool:
        was = installed["value"]
        installed["value"] = False
        return was

    monkeypatch.setattr(login_service, "is_supported", lambda: True)
    monkeypatch.setattr(login_service, "is_installed", lambda: installed["value"])
    monkeypatch.setattr(login_service, "install", _install)
    monkeypatch.setattr(login_service, "uninstall", _uninstall)
    monkeypatch.setattr(login_service, "plist_path", lambda: plist)

    res = runner.invoke(app, ["daemon", "service", "install"])
    assert res.exit_code == 0, res.output
    assert f"login service installed: {plist}" in res.output
    assert installed["value"] is True

    res = runner.invoke(app, ["daemon", "service", "status"])
    assert res.exit_code == 0, res.output
    assert f"installed: {plist}" in res.output

    res = runner.invoke(app, ["daemon", "service", "uninstall"])
    assert res.exit_code == 0, res.output
    assert "login service removed" in res.output
    assert installed["value"] is False

    # No daemon, so no database and no audit table was ever reached.
    assert not (home / ".coffer" / "coffer.db").exists()

    res = runner.invoke(app, ["daemon", "idle", "show"])
    assert res.exit_code != 0
    assert "No such command" in res.output
    assert not (home / ".coffer" / "daemon.json").exists()


@pytest.mark.acceptance(
    spec="daemon", scenario="an idle window left in the daemon config is ignored and dropped"
)
def test_an_idle_window_left_in_the_config_is_ignored_and_dropped(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file an earlier build wrote still starts the daemon on its pinned
    port with no idle watcher, and the next write drops the stale key."""
    import asyncio

    from coffer.infrastructure.daemon import entry

    path = home / ".coffer" / "daemon-config.json"
    path.write_text(json.dumps({"port": 8123, "idle_shutdown_hours": 6, "machine_name": "lap"}))

    # The daemon starts: it binds the pinned port, and the only watcher it
    # runs beside uvicorn is the supersession check — nothing counts idleness.
    assert daemon_config.effective_port() == 8123
    watchers: set[str] = set()

    class _FakeServer:
        def __init__(self, config: object) -> None:
            self.started = False
            self.should_exit = False

        async def serve(self) -> None:
            self.started = True
            await asyncio.sleep(0.05)  # let _run_server start its watchers
            current = asyncio.current_task()
            watchers.update(
                t.get_name() for t in asyncio.all_tasks() if t is not current and not t.done()
            )

    class _Sock:
        def fileno(self) -> int:
            return 7

    monkeypatch.setattr(entry.uvicorn, "Server", _FakeServer)
    entry._run_server(_Sock(), lambda: None)  # type: ignore[arg-type]
    assert "daemon-orphan-evictor" in watchers
    assert not any("idle" in name for name in watchers), watchers

    res = runner.invoke(app, ["daemon", "port", "set", "8200"])
    assert res.exit_code == 0, res.output

    written = _config(home)
    assert written["port"] == 8200
    assert "idle_shutdown_hours" not in written
    # Merge semantics hold for every other key.
    assert written["machine_name"] == "lap"
