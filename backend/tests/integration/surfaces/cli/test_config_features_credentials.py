"""``coffer config`` for ``feature.<key>`` and ``credentials.storage``.

Features run against the real app. The master key is exercised against a
stand-in route instead: the real relocation would move a key into this
machine's keychain, and what is under test here is that the command goes
through the daemon's route — and only through it — with its value refused
before the call.
"""

from __future__ import annotations

import ast
import json
import pathlib
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from typer.testing import CliRunner

from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli.main import app as cli_app
from tests.support.features import FAKE_FEATURE, register_fake_feature

from ._real_app import boot, extract_json

_runner = CliRunner()


@pytest.fixture
def daemon(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """The real app, with a test-only feature registered before it boots."""
    register_fake_feature(monkeypatch, route_prefixes=())
    yield from boot(tmp_path, monkeypatch)


@pytest.fixture
def bare_daemon(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """The real app over the real, empty registry."""
    yield from boot(tmp_path, monkeypatch)


def _daemon_config(home: pathlib.Path) -> dict[str, Any]:
    path = home / ".coffer" / "daemon-config.json"
    return dict(json.loads(path.read_text())) if path.exists() else {}


def test_a_feature_is_listed_and_switched_through_the_daemon(
    daemon: TestClient, tmp_path: Any
) -> None:
    listed = _runner.invoke(cli_app, ["config", "list", "feature.", "--json"])
    assert listed.exit_code == 0, listed.output
    rows = {r["key"]: r for r in extract_json(listed.output)["settings"]}
    registered = {f["key"] for f in daemon.get("/daemon/features").json()["features"]}
    assert set(rows) == {f"feature.{k}" for k in registered}
    assert all(r["type"] == "on|off" and r["note"] for r in rows.values())

    on = _runner.invoke(cli_app, ["config", "set", f"feature.{FAKE_FEATURE}", "on"])
    assert on.exit_code == 0, on.output
    assert "set on this machine" in on.output
    assert _daemon_config(tmp_path)["features"][FAKE_FEATURE] is True
    assert (
        extract_json(
            _runner.invoke(cli_app, ["config", "get", f"feature.{FAKE_FEATURE}", "--json"]).output
        )["value"]
        is True
    )

    bad = _runner.invoke(cli_app, ["config", "set", f"feature.{FAKE_FEATURE}", "maybe"])
    assert bad.exit_code == 6 and "on or off" in bad.output
    unknown = _runner.invoke(cli_app, ["config", "set", "feature.nope", "on"])
    assert unknown.exit_code == 4 and "feature.nope" in unknown.output


@pytest.mark.acceptance(
    spec="experimental-features", scenario="an empty registry lists no features"
)
def test_an_empty_registry_lists_nothing_and_exits_0(bare_daemon: TestClient) -> None:
    listed = _runner.invoke(cli_app, ["config", "list", "feature."])
    assert listed.exit_code == 0, listed.output
    assert listed.output.strip() == ""
    as_json = _runner.invoke(cli_app, ["config", "list", "feature.", "--json"])
    assert as_json.exit_code == 0, as_json.output
    assert extract_json(as_json.output)["settings"] == []


@pytest.mark.acceptance(
    spec="experimental-features", scenario="unsetting a feature returns it to the channel default"
)
def test_unsetting_a_feature_returns_it_to_the_channel_default(
    daemon: TestClient, tmp_path: Any
) -> None:
    assert (
        _runner.invoke(cli_app, ["config", "set", f"feature.{FAKE_FEATURE}", "off"]).exit_code == 0
    )
    unset = _runner.invoke(cli_app, ["config", "unset", f"feature.{FAKE_FEATURE}"])
    assert unset.exit_code == 0, unset.output
    assert FAKE_FEATURE not in _daemon_config(tmp_path).get("features", {})
    rows = {
        r["key"]: r
        for r in extract_json(
            _runner.invoke(cli_app, ["config", "list", "feature.", "--json"]).output
        )["settings"]
    }
    registered = {r["key"] for r in daemon.get("/daemon/features").json()["features"]}
    assert set(rows) == {f"feature.{key}" for key in registered}
    assert rows[f"feature.{FAKE_FEATURE}"]["note"] == "channel default"
    channel = daemon.get("/daemon/features").json()["channel"]
    assert rows[f"feature.{FAKE_FEATURE}"]["value"] is (channel == "dev")


# --- credentials.storage --------------------------------------------------------------


@pytest.fixture
def storage_route(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any]]:
    calls: list[tuple[str, Any]] = []
    state = {"master_key_storage": "file"}
    app = FastAPI()

    @app.get("/api/v1/settings/credentials")
    async def read() -> dict[str, str]:
        calls.append(("GET", None))
        return state

    @app.put("/api/v1/settings/credentials")
    async def write(body: dict[str, str]) -> dict[str, str]:
        calls.append(("PUT", body))
        state.update(body)
        return state

    client = TestClient(app, base_url="http://localhost/api/v1")
    info = DaemonInfo(
        version=1, pid=1, port=9999, token="t", started_at=datetime.now(tz=UTC), binary_path="/t"
    )
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (client, info))
    return calls


@pytest.mark.acceptance(spec="credentials", scenario="move the master key with the config command")
def test_the_master_key_moves_through_the_config_command(
    storage_route: list[tuple[str, Any]],
) -> None:
    assert (
        _runner.invoke(cli_app, ["config", "get", "credentials.storage"]).output.strip() == "file"
    )

    moved = _runner.invoke(cli_app, ["config", "set", "credentials.storage", "keychain"])
    assert moved.exit_code == 0, moved.output
    assert ("PUT", {"master_key_storage": "keychain"}) in storage_route

    calls_before = list(storage_route)
    refused = _runner.invoke(cli_app, ["config", "set", "credentials.storage", "vault"])
    assert refused.exit_code != 0
    assert "file" in refused.output and "keychain" in refused.output
    assert storage_route == calls_before

    back = _runner.invoke(cli_app, ["config", "unset", "credentials.storage"])
    assert back.exit_code == 0
    assert storage_route[-1] == ("PUT", {"master_key_storage": "file"})


_CLI = pathlib.Path(__file__).resolve().parents[4] / "coffer" / "surfaces" / "cli"
_CONFIG_MODULES = ("config_cmd.py", "_config_keys.py", "_config_registry.py", "_config_engine.py")


@pytest.mark.acceptance(
    spec="credentials", scenario="the config command reaches the master key only through the daemon"
)
def test_the_config_command_imports_no_credential_code(
    storage_route: list[tuple[str, Any]],
) -> None:
    for name in _CONFIG_MODULES:
        tree = ast.parse((_CLI / name).read_text())
        imported = {
            n.module if isinstance(n, ast.ImportFrom) else alias.name
            for n in ast.walk(tree)
            if isinstance(n, ast.Import | ast.ImportFrom)
            for alias in n.names
        }
        assert not any(m and (m == "keyring" or m.startswith("keyring.")) for m in imported), name
        assert not any(m and m.startswith("coffer.infrastructure.credentials") for m in imported), (
            name
        )

    assert _runner.invoke(cli_app, ["config", "get", "credentials.storage"]).exit_code == 0
    assert storage_route == [("GET", None)]
