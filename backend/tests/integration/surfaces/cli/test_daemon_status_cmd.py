"""`coffer daemon status` is read-only: with no daemon running it reports
"not running" and exits 3, and never spawns one."""

import json

import pytest
from typer.testing import CliRunner

from coffer.surfaces.cli import _client as cli_client
from coffer.surfaces.cli.main import app


@pytest.fixture
def no_daemon(tmp_path, monkeypatch):
    """An empty HOME, with every spawn path turned into a test failure."""
    monkeypatch.setenv("HOME", str(tmp_path))
    spawned: list[str] = []

    def _record_spawn():
        spawned.append("spawn")
        return None

    monkeypatch.setattr(cli_client, "_spawn_daemon", _record_spawn)
    monkeypatch.setattr(cli_client, "_DAEMON_BOOT_TIMEOUT", 0.05)
    return tmp_path, spawned


@pytest.mark.acceptance(
    spec="daemon", scenario="status reports a stopped daemon without starting one"
)
def test_status_without_a_daemon_says_not_running_and_spawns_nothing(no_daemon):
    home, spawned = no_daemon
    res = CliRunner().invoke(app, ["daemon", "status"])
    assert res.exit_code == 3
    assert res.stdout.splitlines() == ["status:  not running"]
    assert spawned == []
    assert not (home / ".coffer" / "daemon.json").exists()


def test_status_json_without_a_daemon_reports_stopped(no_daemon):
    _home, spawned = no_daemon
    res = CliRunner().invoke(app, ["daemon", "status", "--json"])
    assert res.exit_code == 3
    assert json.loads(res.stdout) == {"status": "stopped"}
    assert spawned == []


def test_status_treats_a_stale_daemon_json_as_not_running(no_daemon):
    """A daemon.json whose port nothing answers on is a crashed daemon."""
    home, spawned = no_daemon
    (home / ".coffer").mkdir()
    (home / ".coffer" / "daemon.json").write_text(
        json.dumps(
            {
                "version": 1,
                "pid": 999999,
                "port": 1,
                "token": "t",
                "started_at": "2026-01-01T00:00:00+00:00",
                "binary_path": "/x",
            }
        )
    )
    res = CliRunner().invoke(app, ["daemon", "status"])
    assert res.exit_code == 3
    assert "not running" in res.stdout
    assert spawned == []
