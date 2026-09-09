"""Integration tests for `coffer sync ...` CLI subcommands (spec 010).

Boots the full FastAPI app (real sync stack, real SQLite + temp HOME), routes
``_cli_client.client_or_exit`` to a TestClient, and drives the CLI against a
real bare git remote.
"""

from __future__ import annotations

import subprocess
from datetime import UTC
from datetime import datetime as dt

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_runner = CliRunner()
_TOKEN = "test-token-sync-cli"


@pytest.fixture
def sync_cli_daemon(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59820")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59829")
    monkeypatch.setenv("COFFER_SYNC_ROOT", str(tmp_path / "sync"))

    app = create_app()
    set_active_token(_TOKEN)
    info = DaemonInfo(
        version=1,
        pid=1,
        port=59820,
        token=_TOKEN,
        started_at=dt.now(tz=UTC),
        binary_path="/test",
    )
    fake = TestClient(
        app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "cli"},
        raise_server_exceptions=False,
    )
    fake.__enter__()

    class _Persistent:
        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *a):  # type: ignore[no-untyped-def]
            return None

        def __getattr__(self, item):  # type: ignore[no-untyped-def]
            return getattr(fake, item)

    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (_Persistent(), info))
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    yield str(bare)
    fake.__exit__(None, None, None)


def test_status_unconfigured(sync_cli_daemon):  # type: ignore[no-untyped-def]
    result = _runner.invoke(cli_app, ["sync", "status"])
    assert result.exit_code == 0, result.output
    assert "unconfigured" in result.output


def test_init_then_status_clean(sync_cli_daemon):  # type: ignore[no-untyped-def]
    bare = sync_cli_daemon
    init = _runner.invoke(cli_app, ["sync", "init", bare])
    assert init.exit_code == 0, init.output
    assert "clean" in init.output

    status = _runner.invoke(cli_app, ["sync", "status"])
    assert status.exit_code == 0, status.output
    assert "clean" in status.output


def test_config_toggle_auto(sync_cli_daemon):  # type: ignore[no-untyped-def]
    bare = sync_cli_daemon
    _runner.invoke(cli_app, ["sync", "init", bare])
    result = _runner.invoke(cli_app, ["sync", "config", "--auto", "on", "--interval", "120"])
    assert result.exit_code == 0, result.output
    assert '"auto": true' in result.output
    assert '"interval_seconds": 120' in result.output


def test_machines_top_level_matches_sync_machines(sync_cli_daemon):  # type: ignore[no-untyped-def]
    """`coffer machines` is the same implementation as `coffer sync machines`
    (Task 15) — byte-identical output, not just an equivalent re-implementation."""
    top_level = _runner.invoke(cli_app, ["machines"])
    assert top_level.exit_code == 0, top_level.output
    nested = _runner.invoke(cli_app, ["sync", "machines"])
    assert nested.exit_code == 0, nested.output
    assert top_level.output == nested.output


def test_machines_top_level_rename_still_works(sync_cli_daemon):  # type: ignore[no-untyped-def]
    """--rename keeps working identically through the top-level alias."""
    result = _runner.invoke(cli_app, ["machines", "--rename", "renamed-box"])
    assert result.exit_code == 0, result.output
    assert "renamed-box" in result.output
