"""Integration tests for `coffer resource` CLI subcommands."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime as dt
from typing import Any

import httpx
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app

_runner = CliRunner()

_ERROR_BODY = (
    '{"error": {"code": "INTERNAL_ERROR", "message": "internal server error", "details": {}}}'
)


# ---------------------------------------------------------------------------
# Helpers for 5xx error simulation
# ---------------------------------------------------------------------------


class _HttpErrorResponse:
    """Fake httpx response that raises HTTPStatusError on raise_for_status()."""

    def __init__(self, status_code: int = 500) -> None:
        self.status_code = status_code
        self._real = httpx.Response(status_code, text=_ERROR_BODY)

    def raise_for_status(self) -> None:
        req = httpx.Request("GET", "http://fake/api/v1/test")
        raise httpx.HTTPStatusError(
            f"Server error '{self.status_code}'",
            request=req,
            response=self._real,
        )

    def json(self) -> Any:
        return self._real.json()


class _HttpErrorClient:
    """Fake client that always returns a 5xx response."""

    def __init__(self, status_code: int = 500) -> None:
        self._status_code = status_code

    def get(self, *_args: Any, **_kwargs: Any) -> _HttpErrorResponse:
        return _HttpErrorResponse(self._status_code)

    def post(self, *_args: Any, **_kwargs: Any) -> _HttpErrorResponse:
        return _HttpErrorResponse(self._status_code)

    def delete(self, *_args: Any, **_kwargs: Any) -> _HttpErrorResponse:
        return _HttpErrorResponse(self._status_code)

    def __enter__(self) -> _HttpErrorClient:
        return self

    def __exit__(self, *_: object) -> None:
        pass


_FAKE_INFO = DaemonInfo(
    version=1, pid=99, port=9999, token="t", started_at=dt.now(tz=UTC), binary_path="/fake"
)


def _register(in_proc_daemon, name: str = "r1", foo: int = 1) -> None:
    """Helper: register a fake_kind resource via the HTTP API (bypasses CLI)."""
    from coffer.surfaces.cli import _client as _cli_client

    # Use the monkeypatched client directly
    client, _info = _cli_client.client_or_exit()
    r = client.post(
        "/resources",
        json={"kind": "fake_kind", "name": name, "config": {"foo": foo}},
    )
    assert r.status_code == 201, r.text


# ---------------------------------------------------------------------------
# resource list
# ---------------------------------------------------------------------------


def test_resource_list_empty(in_proc_daemon):
    result = _runner.invoke(app, ["resource", "list", "--json"])
    assert result.exit_code == 0, result.output
    import json

    data = json.loads(result.output)
    # Stable top-level key per spec scenario: `resources` for `resource list`.
    assert data == {"resources": []}


def test_resource_list_shows_registered(in_proc_daemon):
    _register(in_proc_daemon)
    result = _runner.invoke(app, ["resource", "list", "--json"])
    assert result.exit_code == 0, result.output
    import json

    items = json.loads(result.output)["resources"]
    assert len(items) == 1
    assert items[0]["ref"] == "fake_kind:r1"


def test_resource_list_filter_kind(in_proc_daemon):
    _register(in_proc_daemon, name="r1")
    result = _runner.invoke(app, ["resource", "list", "--kind", "fake_kind", "--json"])
    assert result.exit_code == 0
    import json

    items = json.loads(result.output)["resources"]
    assert len(items) == 1


# ---------------------------------------------------------------------------
# resource show
# ---------------------------------------------------------------------------


def test_resource_show_existing(in_proc_daemon):
    _register(in_proc_daemon)
    result = _runner.invoke(app, ["resource", "show", "fake_kind:r1"])
    assert result.exit_code == 0, result.output
    assert "fake_kind:r1" in result.output


def test_resource_show_not_found(in_proc_daemon):
    result = _runner.invoke(app, ["resource", "show", "fake_kind:nope"])
    assert result.exit_code == 4


# ---------------------------------------------------------------------------
# resource enable / disable
# ---------------------------------------------------------------------------


def test_resource_enable_disable(in_proc_daemon):
    _register(in_proc_daemon)
    result = _runner.invoke(app, ["resource", "disable", "fake_kind:r1"])
    assert result.exit_code == 0, result.output
    assert "disabled" in result.output

    result = _runner.invoke(app, ["resource", "enable", "fake_kind:r1"])
    assert result.exit_code == 0, result.output
    assert "enabled" in result.output


# ---------------------------------------------------------------------------
# resource delete
# ---------------------------------------------------------------------------


def test_resource_delete_with_force(in_proc_daemon):
    _register(in_proc_daemon)
    result = _runner.invoke(app, ["resource", "delete", "--force", "fake_kind:r1"])
    assert result.exit_code == 0, result.output
    assert "deleted" in result.output

    # Confirm gone
    result2 = _runner.invoke(app, ["resource", "show", "fake_kind:r1"])
    assert result2.exit_code == 4


def test_resource_delete_not_found_with_force(in_proc_daemon):
    result = _runner.invoke(app, ["resource", "delete", "--force", "fake_kind:ghost"])
    # Service raises ResourceNotFound → HTTP 404 → CLI exits with code 4
    assert result.exit_code == 4


# ---------------------------------------------------------------------------
# T2 — 5xx errors are rendered via check(), not bare raise_for_status()
# ---------------------------------------------------------------------------


def test_resource_show_5xx_renders_message_exits_nonzero(monkeypatch):
    """resource show on a 5xx response must NOT raise a Traceback; must exit non-zero."""
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (_HttpErrorClient(), _FAKE_INFO))
    result = _runner.invoke(app, ["resource", "show", "fake_kind:anything"])
    assert result.exit_code != 0, "expected non-zero exit on 5xx"
    assert "Traceback" not in (result.output or ""), "Traceback leaked to output"


def test_resource_delete_5xx_renders_message_exits_nonzero(monkeypatch):
    """resource delete on a 5xx response must NOT raise a Traceback; must exit non-zero."""
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (_HttpErrorClient(), _FAKE_INFO))
    result = _runner.invoke(app, ["resource", "delete", "--force", "fake_kind:anything"])
    assert result.exit_code != 0, "expected non-zero exit on 5xx"
    assert "Traceback" not in (result.output or ""), "Traceback leaked to output"
