"""Acceptance tests for US4 — CLI parity with the UI.

Scenario 1: every UI-visible operation has a CLI subcommand.
Scenario 2: the CLI surfaces errors in the same human-readable form as the UI.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app
from coffer.surfaces.http.auth import set_active_token

runner = CliRunner()


@pytest.mark.acceptance(
    spec="001-mcp-gateway",
    scenario="command line covers every visual operation",
)
def test_cli_covers_every_visual_operation():
    """Every UI-visible operation has a CLI subcommand.

    For each subcommand group we invoke ``--help`` and assert that every
    operation name the UI exposes is present in the help output.
    """
    expected_subcommands: dict[str, list[str]] = {
        "daemon": ["start", "stop", "status", "backup", "rotate-token"],
        "resource": ["list", "show", "enable", "disable", "delete"],
        "audit": ["list"],
        "retention": ["list", "set", "prune-now"],
        "mcp": [
            "add",
            "remove",
            "list",
            "show",
            "refresh",
            "test",
            "tool",
            "resource",
            "prompt",
            "invocations",
        ],
        "mcp tool": ["list", "enable", "disable"],
        "mcp resource": ["list", "enable", "disable"],
        "mcp prompt": ["list", "enable", "disable"],
        "keychain": ["set", "get", "list", "delete"],
    }
    for group_path, names in expected_subcommands.items():
        parts = group_path.split()
        result = runner.invoke(app, [*parts, "--help"])
        assert result.exit_code == 0, (
            f"{group_path} --help exited {result.exit_code}:\n{result.output}"
        )
        for name in names:
            assert name in result.output, (
                f"'{group_path}' help is missing subcommand '{name}':\n{result.output}"
            )


@pytest.mark.acceptance(
    spec="001-mcp-gateway",
    scenario="command line surfaces same errors",
)
def test_cli_surfaces_same_errors(tmp_path, monkeypatch):
    """The CLI's error output matches the UI's user-facing message.

    Drive a representative failure scenario (spawn timeout / daemon
    unreachable) through the CLI and verify:
    - No raw Python traceback leaks to the user.
    - The exit code is within the documented range (1-8).
    - A human-readable message is present on stderr or stdout.

    ADR-006: client_or_exit() now auto-spawns on missing daemon.json. We
    simulate a spawn-that-times-out so the DaemonNotRunning (exit 3) path
    is exercised.
    """
    import coffer.surfaces.cli._client as cli_client

    monkeypatch.setenv("HOME", str(tmp_path))
    # Prevent real daemon spawn; simulate timeout.
    monkeypatch.setattr(cli_client, "_spawn_daemon", lambda: None)
    monkeypatch.setattr(cli_client, "_DAEMON_BOOT_TIMEOUT", 0.05)

    result = runner.invoke(app, ["mcp", "show", "nope"])

    combined = result.output + (result.stderr or "")

    # spawn timeout → daemon boot failed → exit 3
    assert result.exit_code == 3, f"unexpected exit code {result.exit_code}:\n{combined}"
    # The CLI must not expose a raw Python traceback to the user.
    assert "Traceback" not in combined, f"raw traceback leaked to user output:\n{combined}"
    # There must be some message output.
    assert combined.strip(), "no output produced on error"


# ---------------------------------------------------------------------------
# T2 — CLI error renderer + --verbose
# ---------------------------------------------------------------------------


def _fake_client_returning_500(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wire CLI to a tiny in-process server that returns 500 for every request."""
    from datetime import UTC
    from datetime import datetime as dt

    err_app = FastAPI()

    @err_app.get("/api/v1/daemon/status")
    def boom() -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": "kaboom", "details": {}}},
        )

    set_active_token("test-tok")
    fake = TestClient(
        err_app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": "test-tok"},
        raise_server_exceptions=False,
    )
    info = DaemonInfo(
        version=1,
        pid=12345,
        port=8000,
        token="test-tok",
        started_at=dt.now(tz=UTC),
        binary_path="/test",
    )
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (fake, info))


def _fake_client_returning_credential_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wire CLI to a server that returns 400 CREDENTIAL_MISSING."""
    from datetime import UTC
    from datetime import datetime as dt

    err_app = FastAPI()

    @err_app.get("/api/v1/daemon/status")
    def cred_missing() -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "CREDENTIAL_MISSING",
                    "message": "credential not found: MY_TOKEN",
                    "details": {},
                }
            },
        )

    set_active_token("test-tok")
    fake = TestClient(
        err_app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": "test-tok"},
        raise_server_exceptions=False,
    )
    info = DaemonInfo(
        version=1,
        pid=12345,
        port=8000,
        token="test-tok",
        started_at=dt.now(tz=UTC),
        binary_path="/test",
    )
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (fake, info))


def test_cli_5xx_shows_actionable_message_not_traceback(monkeypatch):
    """A 5xx HTTP error must produce a user-readable message, not a traceback."""
    _fake_client_returning_500(monkeypatch)
    result = runner.invoke(app, ["daemon", "status"])
    combined = result.output + (result.stderr or "")
    assert result.exit_code != 0, f"expected non-zero exit, got 0:\n{combined}"
    assert "Traceback" not in combined, f"raw traceback leaked:\n{combined}"
    assert combined.strip(), "no output on error"


def test_cli_verbose_shows_trace(monkeypatch):
    """With --verbose, the error includes HTTP status/detail context."""
    _fake_client_returning_500(monkeypatch)
    result = runner.invoke(app, ["--verbose", "daemon", "status"])
    combined = result.output + (result.stderr or "")
    assert result.exit_code != 0, f"expected non-zero exit, got 0:\n{combined}"
    # --verbose must include extra context (the traceback text itself)
    assert "HTTPStatusError" in combined or "500" in combined, (
        f"--verbose output missing error context:\n{combined}"
    )


def test_cli_credential_missing_maps_to_exit_8(monkeypatch):
    """CREDENTIAL_MISSING error code must map to exit code 8."""
    _fake_client_returning_credential_missing(monkeypatch)
    result = runner.invoke(app, ["daemon", "status"])
    assert result.exit_code == 8, (
        f"expected exit code 8 (CREDENTIAL_ISSUE), got {result.exit_code}:\n{result.output}"
    )
