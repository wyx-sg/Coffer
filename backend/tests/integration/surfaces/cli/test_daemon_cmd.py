"""`coffer daemon port` + the fixed-port pre-flight in `coffer daemon start`.

Every test runs under a throwaway ``HOME`` so nothing here can read or write
the developer's real ``~/.coffer``. These deliberately exercise the
no-daemon-running path: that is the state a bad fixed port causes, and the
state the whole sub-group has to remain usable in.
"""

from __future__ import annotations

import json
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli import daemon_cmd, daemon_port_cmd
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


def test_port_clear_removes_the_fixed_port(home: Path) -> None:
    assert runner.invoke(app, ["daemon", "port", "set", "8123"]).exit_code == 0

    res = runner.invoke(app, ["daemon", "port", "clear"])
    assert res.exit_code == 0, res.output
    assert "automatic" in res.output
    assert _config(home)["port"] is None

    payload = json.loads(runner.invoke(app, ["daemon", "port", "show", "--json"]).stdout)
    assert payload["configured_port"] is None


def test_port_show_reports_automatic_when_nothing_is_configured(home: Path) -> None:
    res = runner.invoke(app, ["daemon", "port", "show"])
    assert res.exit_code == 0, res.output
    assert "automatic" in res.output
    assert not (home / ".coffer" / "daemon-config.json").exists()


def test_port_show_flags_a_config_file_it_cannot_read(home: Path) -> None:
    """A hand-mangled config is reported where the user can act on it — the
    daemon itself only warns into a log and falls back to automatic."""
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


def test_start_refuses_when_the_fixed_port_is_held(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pre-flight names the conflict in the terminal instead of letting the
    spawn time out into "check daemon.log"."""
    squatter = socket.socket()
    squatter.bind(("127.0.0.1", 0))
    squatter.listen(5)
    port = squatter.getsockname()[1]
    try:
        assert runner.invoke(app, ["daemon", "port", "set", str(port)]).exit_code == 0

        def _must_not_spawn(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("start must not spawn a daemon onto a held fixed port")

        monkeypatch.setattr(daemon_cmd.subprocess, "Popen", _must_not_spawn)

        res = runner.invoke(app, ["daemon", "start"])
    finally:
        squatter.close()

    assert res.exit_code != 0
    assert str(port) in res.output
    assert "coffer daemon port set" in res.output
    assert not (home / ".coffer" / "daemon.json").exists()


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


class _FakeClient:
    """Records the one request the command makes, and answers the contract."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, Any]] = []

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def put(self, path: str, json: Any = None) -> httpx.Response:
        self.calls.append((path, json))
        return httpx.Response(
            200, json=self.payload, request=httpx.Request("PUT", f"http://d{path}")
        )


def test_port_set_goes_through_a_running_daemon(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With a daemon up the change is made through its API, so it is audited —
    the direct file write is only the no-daemon fallback."""
    info = _live(monkeypatch, 8000)
    fake = _FakeClient({"configured_port": 8123, "effective_port": 8000, "restart_required": True})
    monkeypatch.setattr(daemon_port_cmd._cli_client, "client_or_exit", lambda: (fake, info))

    res = runner.invoke(app, ["daemon", "port", "set", "8123"])
    assert res.exit_code == 0, res.output
    assert fake.calls == [("/settings/daemon", {"port": 8123})]
    assert "coffer daemon restart" in res.output
    # The daemon owns the file in this path; the CLI must not have written it.
    assert not (home / ".coffer" / "daemon-config.json").exists()


def test_port_clear_goes_through_a_running_daemon(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del home  # only needed so nothing can touch the developer's real ~/.coffer
    info = _live(monkeypatch, 8000)
    fake = _FakeClient({"configured_port": None, "effective_port": 8000, "restart_required": False})
    monkeypatch.setattr(daemon_port_cmd._cli_client, "client_or_exit", lambda: (fake, info))

    res = runner.invoke(app, ["daemon", "port", "clear"])
    assert res.exit_code == 0, res.output
    assert fake.calls == [("/settings/daemon", {"port": None})]
    assert "automatic" in res.output
    assert "coffer daemon restart" not in res.output


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
