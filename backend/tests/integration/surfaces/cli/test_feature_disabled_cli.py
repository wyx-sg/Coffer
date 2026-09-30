"""A feature pinned by the environment refused through `coffer config`, and the
CLI's one line for ``FEATURE_DISABLED``. Listing and switching features is
covered with `coffer config` in test_config_features_secrets.py.

The CLI talks to an in-process app through a ``TestClient`` under a throwaway
HOME, so the switches land in ``tmp_path`` and nothing reaches ``~/.coffer``.
The feature is a test-only one, since nothing is experimental right now.
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
from tests.support.features import FAKE_FEATURE, register_fake_feature

runner = CliRunner()
_TOKEN = "cli-token"


def _gated() -> APIRouter:
    r = APIRouter(prefix="/api/v1/sync", dependencies=[Depends(require_feature(FAKE_FEATURE))])

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
    register_fake_feature(monkeypatch, route_prefixes=("/api/v1/sync",))
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


def test_setting_a_pinned_feature_exits_conflict(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A feature pinned by ``COFFER_FEATURES`` cannot be switched from the
    CLI; the refusal names the variable rather than pretending to write."""
    monkeypatch.setenv(daemon_config.FEATURES_ENV, f"{FAKE_FEATURE}=off")
    set_feature_service(build_feature_service())
    res = runner.invoke(cli_app, ["config", "set", f"feature.{FAKE_FEATURE}", "on"])
    assert res.exit_code == int(ExitCode.CONFLICT), res.output
    assert "COFFER_FEATURES" in res.stderr
    assert not (home / ".coffer" / "daemon-config.json").exists()


def test_a_switched_off_features_command_prints_one_line_and_exits_1(home: Path) -> None:
    off = runner.invoke(cli_app, ["config", "set", f"feature.{FAKE_FEATURE}", "off"])
    assert off.exit_code == 0, off.output
    res = runner.invoke(cli_app, ["sync", "now"])
    assert res.exit_code == 1
    [line] = res.stderr.splitlines()
    assert line.startswith(f"{FAKE_FEATURE} is switched off on this machine — run: coffer ")


def test_render_http_error_maps_feature_disabled_to_one_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = httpx.Request("GET", "http://localhost/api/v1/sync/status")
    response = httpx.Response(
        404,
        json={
            "error": {
                "code": "FEATURE_DISABLED",
                "message": f"{FAKE_FEATURE} is switched off",
                "details": {"feature": FAKE_FEATURE},
            }
        },
        request=request,
    )
    err = httpx.HTTPStatusError("404", request=request, response=response)
    code = cli_client.render_http_error(err, verbose=False)
    assert code == ExitCode.GENERIC
    [line] = capsys.readouterr().err.splitlines()
    assert line.startswith(f"{FAKE_FEATURE} is switched off on this machine — run: coffer ")
