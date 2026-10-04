"""``coffer config list|get|set|unset`` over the pre-bind key registry.

``daemon.port`` is the only key and runs with no daemon at all.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from typer.testing import CliRunner

from coffer.infrastructure.daemon import bootstrap
from coffer.infrastructure.daemon import config as daemon_config
from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli.main import app as cli_app

_runner = CliRunner()


def _run(*args: str) -> Any:
    return _runner.invoke(cli_app, list(args), env={"COLUMNS": "250"})


# --- daemon.port: no daemon at all ---------------------------------------------------


@pytest.fixture
def no_daemon(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("HOME", str(tmp_path))

    def _refuse() -> Any:
        raise AssertionError("daemon.port must not reach for a daemon")

    monkeypatch.setattr(_cli_client, "client_or_exit", _refuse)
    monkeypatch.setattr(bootstrap, "live_daemon", lambda: None)
    return tmp_path


@pytest.mark.acceptance(
    spec="daemon", scenario="the port key is read and changed with no daemon running"
)
@pytest.mark.acceptance(
    spec="resource-framework", scenario="a setting is read, changed and returned to its default"
)
def test_the_port_key_is_read_changed_and_unset_with_no_daemon(no_daemon: Any) -> None:
    config_file = no_daemon / ".coffer" / "daemon-config.json"

    first = _run("config", "get", "daemon.port")
    assert first.exit_code == 0, first.output
    assert first.output.strip() == "38470"

    changed = _run("config", "set", "daemon.port", "8123")
    assert changed.exit_code == 0, changed.output
    assert json.loads(config_file.read_text())["port"] == 8123
    assert daemon_config.read_fixed_port() == 8123
    assert _run("config", "get", "daemon.port").output.strip() == "8123"

    back = _run("config", "unset", "daemon.port")
    assert back.exit_code == 0, back.output
    assert json.loads(config_file.read_text()).get("port") is None
    assert _run("config", "get", "daemon.port").output.strip() == "38470"

    listed = _run("config", "list", "daemon.", "--json")
    assert listed.exit_code == 0, listed.output
    [row] = json.loads(listed.output)["settings"]
    assert row["key"] == "daemon.port" and row["value"] == 38470 and row["default"] == 38470
    assert row["type"] == "port" and row["help"]
    table = _run("config", "list", "daemon.")
    assert "daemon.port" in table.output and "38470" in table.output


@pytest.mark.acceptance(
    spec="resource-framework", scenario="an invalid setting is refused before any write"
)
def test_the_port_key_refuses_an_unbindable_port(no_daemon: Any) -> None:
    r = _run("config", "set", "daemon.port", "80")
    assert r.exit_code == 6
    assert "between 1024 and 65535" in r.output
    assert daemon_config.read_fixed_port() is None


def test_an_unknown_key_is_refused(no_daemon: Any) -> None:
    for argv in (("get", "engine.model"), ("set", "feature.sync", "on"), ("unset", "nope")):
        r = _run("config", *argv)
        assert r.exit_code == 4, r.output
        assert "unknown setting" in r.output
    assert _run("config", "list", "engine.").exit_code == 4
