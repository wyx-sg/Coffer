"""`coffer daemon features list|enable|disable`, the channel in `coffer daemon
status`, and the CLI's one line for ``FEATURE_DISABLED``.

The CLI talks to an in-process app through a ``TestClient`` under a throwaway
HOME, so the switches land in ``tmp_path`` and nothing reaches ``~/.coffer``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi import APIRouter, Depends, FastAPI
from starlette.testclient import TestClient
from typer.testing import CliRunner

from coffer.infrastructure.daemon import config as daemon_config
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli import _client as cli_client
from coffer.surfaces.cli._options import ExitCode
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http import feature_dependencies
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.daemon_routes import router as daemon_router
from coffer.surfaces.http.feature_dependencies import (
    build_feature_service,
    require_feature,
    set_feature_service,
)
from coffer.surfaces.http.feature_routes import router as feature_router

runner = CliRunner()
_TOKEN = "cli-token"


def _gated() -> APIRouter:
    r = APIRouter(prefix="/api/v1/sync", dependencies=[Depends(require_feature("vault_sync"))])

    @r.post("/run")
    async def sync_run() -> dict[str, str]:
        return {"state": "idle"}

    return r


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    h = tmp_path / "home"
    (h / ".coffer").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.delenv(daemon_config.FEATURES_ENV, raising=False)
    prior = feature_dependencies._feature_service
    set_active_token(_TOKEN)

    def _connect() -> tuple[httpx.Client, DaemonInfo]:
        app = FastAPI()
        err_handlers.register(app)
        app.include_router(daemon_router)
        app.include_router(feature_router)
        app.include_router(_gated())
        client = TestClient(
            app,
            base_url="http://localhost/api/v1",
            headers={"X-Coffer-Token": _TOKEN},
            raise_server_exceptions=False,
        )
        info = DaemonInfo(
            version=1,
            pid=4242,
            port=8000,
            token=_TOKEN,
            started_at=datetime.now(tz=UTC),
            binary_path="/test",
        )
        return client, info

    set_feature_service(build_feature_service())
    monkeypatch.setattr(cli_client, "client_or_exit", _connect)
    monkeypatch.setattr(cli_client, "daemon_is_running", lambda: True)
    yield h
    set_active_token(None)
    feature_dependencies._feature_service = prior


def _config(home: Path) -> dict[str, object]:
    return json.loads((home / ".coffer" / "daemon-config.json").read_text())  # type: ignore[no-any-return]


def test_list_prints_the_channel_and_every_feature(home: Path) -> None:
    res = runner.invoke(cli_app, ["daemon", "features", "list"])
    assert res.exit_code == 0, res.output
    lines = res.stdout.splitlines()
    assert lines[0] == "channel: dev"
    assert [line.split()[:2] for line in lines[1:]] == [
        ["vault_sync", "on"],
        ["knowledge", "on"],
        ["memory", "on"],
    ]
    assert "channel default" in lines[1]


def test_list_json_is_the_route_payload(home: Path) -> None:
    res = runner.invoke(cli_app, ["daemon", "features", "list", "--json"])
    assert res.exit_code == 0, res.output
    payload = json.loads(res.stdout)
    assert payload["channel"] == "dev"
    assert [f["key"] for f in payload["features"]] == ["vault_sync", "knowledge", "memory"]


def test_disable_then_enable_writes_the_setting(home: Path) -> None:
    res = runner.invoke(cli_app, ["daemon", "features", "disable", "memory"])
    assert res.exit_code == 0, res.output
    assert res.stdout.split()[:2] == ["memory", "off"]
    assert "set on this machine" in res.stdout
    assert _config(home) == {"features": {"memory": False}}

    res = runner.invoke(cli_app, ["daemon", "features", "enable", "memory"])
    assert res.exit_code == 0, res.output
    assert res.stdout.split()[:2] == ["memory", "on"]
    assert _config(home) == {"features": {"memory": True}}


def test_enable_an_unknown_key_exits_not_found(home: Path) -> None:
    res = runner.invoke(cli_app, ["daemon", "features", "enable", "workflow"])
    assert res.exit_code == int(ExitCode.NOT_FOUND)
    assert "workflow" in res.stderr
    assert not (home / ".coffer" / "daemon-config.json").exists()


def test_enable_a_pinned_key_exits_conflict(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(daemon_config.FEATURES_ENV, "knowledge=off")
    set_feature_service(build_feature_service())
    res = runner.invoke(cli_app, ["daemon", "features", "enable", "knowledge"])
    assert res.exit_code == int(ExitCode.CONFLICT)
    assert "COFFER_FEATURES" in res.stderr


def test_status_prints_the_channel(home: Path) -> None:
    res = runner.invoke(cli_app, ["daemon", "status"])
    assert res.exit_code == 0, res.output
    assert "channel: dev" in res.stdout.splitlines()


def test_a_switched_off_features_command_prints_one_line_and_exits_1(home: Path) -> None:
    assert runner.invoke(cli_app, ["daemon", "features", "disable", "vault_sync"]).exit_code == 0
    res = runner.invoke(cli_app, ["sync", "now"])
    assert res.exit_code == 1
    assert res.stderr.splitlines() == [
        "vault_sync is switched off on this machine — run: coffer daemon features enable vault_sync"
    ]


def test_render_http_error_maps_feature_disabled_to_one_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = httpx.Request("GET", "http://localhost/api/v1/sync/status")
    response = httpx.Response(
        404,
        json={
            "error": {
                "code": "FEATURE_DISABLED",
                "message": "vault_sync is switched off",
                "details": {"feature": "vault_sync"},
            }
        },
        request=request,
    )
    err = httpx.HTTPStatusError("404", request=request, response=response)
    code = cli_client.render_http_error(err, verbose=False)
    assert code == ExitCode.GENERIC
    assert capsys.readouterr().err.splitlines() == [
        "vault_sync is switched off on this machine — run: coffer daemon features enable vault_sync"
    ]
