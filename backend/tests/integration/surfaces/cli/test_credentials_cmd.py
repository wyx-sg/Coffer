"""Integration tests for `coffer credentials ...` subcommands.

Spec 006: every credentials subcommand goes through the daemon HTTP API — the
CLI never touches credential storage in-process. These tests drive the CLI
against a fake daemon client (an in-memory stand-in for the daemon's
/api/v1/credentials routes) injected via `client_or_exit`.
"""

from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime as dt
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fake daemon — an in-memory implementation of the /api/v1/credentials routes
# so the CLI's HTTP round-trips can be exercised without a real daemon.
# ---------------------------------------------------------------------------

_CREDENTIALS_PREFIX = "/credentials/"


class _Resp:
    def __init__(self, status_code: int, body: Any) -> None:
        self.status_code = status_code
        self._body = body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            req = httpx.Request("GET", "http://fake")
            resp = httpx.Response(self.status_code, json=self._body)
            raise httpx.HTTPStatusError("error", request=req, response=resp)

    def json(self) -> Any:
        return self._body


class _FakeDaemon:
    """In-memory credentials + resource enumeration behind the daemon HTTP shape."""

    def __init__(
        self,
        store: dict[str, str] | None = None,
        resources: list[dict] | None = None,
        master_key_storage: str = "file",
    ) -> None:
        self.store: dict[str, str] = dict(store or {})
        self.resources = resources or []
        self.master_key_storage = master_key_storage

    def post(self, path: str, json: dict | None = None, **_: Any) -> _Resp:
        assert path == "/credentials"
        assert json is not None
        self.store[json["ref"]] = json["value"]
        return _Resp(204, None)

    def get(self, path: str, **_: Any) -> _Resp:
        if path == "/resources":
            return _Resp(200, {"resources": self.resources})
        if path == "/settings/credentials":
            return _Resp(200, {"master_key_storage": self.master_key_storage})
        if path.endswith("/exists"):
            ref = path[len(_CREDENTIALS_PREFIX) : -len("/exists")]
            return _Resp(200, {"present": ref in self.store})
        if path.startswith(_CREDENTIALS_PREFIX):
            ref = path[len(_CREDENTIALS_PREFIX) :]
            if ref in self.store:
                return _Resp(200, {"value": self.store[ref]})
            return _Resp(404, {"error": {"code": "NOT_FOUND", "message": "not found"}})
        raise AssertionError(f"unexpected GET {path}")

    def put(self, path: str, json: dict | None = None, **_: Any) -> _Resp:
        assert path == "/settings/credentials"
        assert json is not None
        self.master_key_storage = json["master_key_storage"]
        return _Resp(200, {"master_key_storage": self.master_key_storage})

    def delete(self, path: str, **_: Any) -> _Resp:
        ref = path[len(_CREDENTIALS_PREFIX) :]
        self.store.pop(ref, None)
        return _Resp(204, None)

    def __enter__(self) -> _FakeDaemon:
        return self

    def __exit__(self, *_: object) -> None:
        pass


def _use_daemon(monkeypatch, daemon: _FakeDaemon) -> None:
    info = DaemonInfo(
        version=1, pid=1, port=9999, token="t", started_at=dt.now(tz=UTC), binary_path="/fake"
    )
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (daemon, info))


@pytest.fixture()
def daemon(monkeypatch):
    d = _FakeDaemon()
    _use_daemon(monkeypatch, d)
    return d


# ---------------------------------------------------------------------------
# set / get round-trip — all via the daemon
# ---------------------------------------------------------------------------


def test_set_writes_through_daemon(daemon):
    result = runner.invoke(app, ["credentials", "set", "my_token", "--value", "supersecret"])
    assert result.exit_code == 0, result.output
    assert "stored: my_token" in result.output
    # The secret was created by the daemon, not the CLI process.
    assert daemon.store["my_token"] == "supersecret"


def test_get_show_reads_through_daemon(daemon):
    daemon.store["my_token"] = "supersecret"
    result = runner.invoke(app, ["credentials", "get", "my_token", "--show"])
    assert result.exit_code == 0, result.output
    assert "supersecret" in result.output


def test_get_without_show_redacts(daemon):
    daemon.store["tok"] = "s3cr3t"
    result = runner.invoke(app, ["credentials", "get", "tok"])
    assert result.exit_code == 0
    assert "[redacted]" in result.output
    assert "s3cr3t" not in result.output


def test_get_missing_exits_4(daemon):
    result = runner.invoke(app, ["credentials", "get", "no_such_ref"])
    assert result.exit_code == 4


def test_get_json(daemon):
    daemon.store["k"] = "v"
    result = runner.invoke(app, ["credentials", "get", "k", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["ref"] == "k"
    assert data["value"] == "[redacted]"


def test_get_json_show(daemon):
    daemon.store["k2"] = "myval"
    result = runner.invoke(app, ["credentials", "get", "k2", "--json", "--show"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["value"] == "myval"


# ---------------------------------------------------------------------------
# delete — via the daemon
# ---------------------------------------------------------------------------


def test_delete_force_removes_through_daemon(daemon):
    daemon.store["to_del"] = "x"
    result = runner.invoke(app, ["credentials", "delete", "to_del", "--force"])
    assert result.exit_code == 0
    assert "deleted: to_del" in result.output
    assert "to_del" not in daemon.store


def test_delete_prompts_for_confirmation(daemon):
    daemon.store["protected"] = "val"
    result = runner.invoke(app, ["credentials", "delete", "protected"], input="n\n")
    assert result.exit_code != 0
    # Declined → still stored.
    assert daemon.store["protected"] == "val"


# ---------------------------------------------------------------------------
# empty value — rejected client-side before any daemon call
# ---------------------------------------------------------------------------


def test_set_empty_value_exits_6(daemon):
    result = runner.invoke(app, ["credentials", "set", "bad_ref", "--value", ""])
    assert result.exit_code == 6
    assert "bad_ref" not in daemon.store


# ---------------------------------------------------------------------------
# list — enumerate refs from /resources, presence via the exists endpoint
# ---------------------------------------------------------------------------


def test_list_reports_refs_from_resources(monkeypatch):
    resources = [
        {"config": {"transport": {"credential_refs": {"Authorization": "gh_pat"}}}},
        {"config": {"transport": {"credential_refs": {"API_KEY": "openai_key"}}}},
    ]
    d = _FakeDaemon(store={"gh_pat": "ghp_test"}, resources=resources)
    _use_daemon(monkeypatch, d)

    result = runner.invoke(app, ["credentials", "list"])
    assert result.exit_code == 0
    assert "gh_pat" in result.output
    assert "openai_key" in result.output


def test_list_json(monkeypatch):
    resources = [
        {"config": {"transport": {"credential_refs": {"KEY": "ref_b"}}}},
        {"config": {"transport": {"credential_refs": {"TOKEN": "ref_a"}}}},
    ]
    d = _FakeDaemon(resources=resources)
    _use_daemon(monkeypatch, d)

    result = runner.invoke(app, ["credentials", "list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["refs"] == ["ref_a", "ref_b"]


def test_list_daemon_spawn_timeout(tmp_path, monkeypatch):
    """list degrades gracefully (exit 0) when the daemon can't be reached."""
    from coffer.surfaces.cli import _client as cli_client

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(cli_client, "_spawn_daemon", lambda: None)
    monkeypatch.setattr(cli_client, "_DAEMON_BOOT_TIMEOUT", 0.05)

    result = runner.invoke(app, ["credentials", "list"])
    assert result.exit_code == 0
    combined = result.output + (result.stderr or "")
    assert "daemon" in combined.lower() or "no known" in combined.lower()


# ---------------------------------------------------------------------------
# list 5xx is rendered via check(), not a bare raise_for_status() traceback
# ---------------------------------------------------------------------------


class _HttpErrorClient:
    def get(self, *_a: Any, **_k: Any) -> _Resp:
        return _Resp(500, {"error": {"code": "INTERNAL_ERROR", "message": "boom"}})

    def __enter__(self) -> _HttpErrorClient:
        return self

    def __exit__(self, *_: object) -> None:
        pass


def test_credentials_list_5xx_renders_message_exits_nonzero(monkeypatch):
    info = DaemonInfo(
        version=1, pid=99, port=9999, token="t", started_at=dt.now(tz=UTC), binary_path="/fake"
    )
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (_HttpErrorClient(), info))
    result = runner.invoke(app, ["credentials", "list"])
    assert result.exit_code != 0
    assert "Traceback" not in (result.output or "")


# ---------------------------------------------------------------------------
# storage subcommand
# ---------------------------------------------------------------------------


def test_storage_shows_current_location(monkeypatch):
    """GET /settings/credentials → master_key_storage shown in stdout."""
    d = _FakeDaemon(master_key_storage="file")
    _use_daemon(monkeypatch, d)

    result = runner.invoke(app, ["credentials", "storage"])
    assert result.exit_code == 0, result.output
    assert "file" in result.output


def test_storage_set_keychain_calls_put(monkeypatch):
    """--set keychain issues PUT /settings/credentials and echoes 'keychain'."""
    d = _FakeDaemon(master_key_storage="file")
    _use_daemon(monkeypatch, d)

    result = runner.invoke(app, ["credentials", "storage", "--set", "keychain"])
    assert result.exit_code == 0, result.output
    assert "keychain" in result.output
    assert d.master_key_storage == "keychain"


def test_storage_rejects_invalid_value(monkeypatch):
    """--set vault exits with INVALID_INPUT (6) without any HTTP call."""
    http_called = []

    class _NoCallDaemon:
        def get(self, *_a: Any, **_k: Any) -> _Resp:
            http_called.append("get")
            return _Resp(200, {"master_key_storage": "file"})

        def put(self, *_a: Any, **_k: Any) -> _Resp:
            http_called.append("put")
            return _Resp(200, {"master_key_storage": "file"})

        def __enter__(self) -> _NoCallDaemon:
            return self

        def __exit__(self, *_: object) -> None:
            pass

    info = DaemonInfo(
        version=1, pid=1, port=9999, token="t", started_at=dt.now(tz=UTC), binary_path="/fake"
    )
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (_NoCallDaemon(), info))

    result = runner.invoke(app, ["credentials", "storage", "--set", "vault"])
    assert result.exit_code == 6
    assert not http_called, "HTTP should not be called for invalid input"
