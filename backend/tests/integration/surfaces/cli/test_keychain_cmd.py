"""Integration tests for `coffer keychain ...` subcommands.

Uses an in-memory keyring backend to avoid touching the real OS keychain.
HTTP calls to the daemon (for `list`) are monkeypatched via a lightweight
stub that returns a canned JSON response.
"""

from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime as dt
from typing import Any

import httpx
import keyring
import keyring.core
import pytest
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _InMemoryKeyring(keyring.backend.KeyringBackend):
    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        self._data: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._data.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._data[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self._data.pop((service, username), None)


@pytest.fixture()
def in_memory_keyring(monkeypatch):
    backend = _InMemoryKeyring()
    monkeypatch.setattr(keyring.core, "_keyring_backend", backend)
    return backend


# ---------------------------------------------------------------------------
# set / get round-trip
# ---------------------------------------------------------------------------


def test_set_and_get_show_round_trip(in_memory_keyring):
    """set REF then get REF --show returns the stored value."""
    result = runner.invoke(app, ["keychain", "set", "my_token", "--value", "supersecret"])
    assert result.exit_code == 0, result.output
    assert "stored: my_token" in result.output

    result = runner.invoke(app, ["keychain", "get", "my_token", "--show"])
    assert result.exit_code == 0, result.output
    assert "supersecret" in result.output


def test_get_without_show_redacts(in_memory_keyring):
    """get without --show returns [redacted], not the value."""
    runner.invoke(app, ["keychain", "set", "tok", "--value", "s3cr3t"])
    result = runner.invoke(app, ["keychain", "get", "tok"])
    assert result.exit_code == 0
    assert "[redacted]" in result.output
    assert "s3cr3t" not in result.output


def test_get_missing_exits_4(in_memory_keyring):
    """get on a non-existent ref exits with code 4 (NOT_FOUND)."""
    result = runner.invoke(app, ["keychain", "get", "no_such_ref"])
    assert result.exit_code == 4


def test_get_json(in_memory_keyring):
    """get --json returns a JSON object with ref + redacted value."""
    runner.invoke(app, ["keychain", "set", "k", "--value", "v"])
    result = runner.invoke(app, ["keychain", "get", "k", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["ref"] == "k"
    assert data["value"] == "[redacted]"


def test_get_json_show(in_memory_keyring):
    """get --json --show includes the real value."""
    runner.invoke(app, ["keychain", "set", "k2", "--value", "myval"])
    result = runner.invoke(app, ["keychain", "get", "k2", "--json", "--show"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["value"] == "myval"


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def test_delete_force_removes_entry(in_memory_keyring):
    """delete --force removes the entry; subsequent get exits 4."""
    runner.invoke(app, ["keychain", "set", "to_del", "--value", "x"])
    result = runner.invoke(app, ["keychain", "delete", "to_del", "--force"])
    assert result.exit_code == 0
    assert "deleted: to_del" in result.output

    result = runner.invoke(app, ["keychain", "get", "to_del"])
    assert result.exit_code == 4


def test_delete_prompts_for_confirmation(in_memory_keyring):
    """delete without --force prompts; answering 'n' exits non-zero."""
    runner.invoke(app, ["keychain", "set", "protected", "--value", "val"])
    result = runner.invoke(app, ["keychain", "delete", "protected"], input="n\n")
    assert result.exit_code != 0
    # Value should still be retrievable
    result2 = runner.invoke(app, ["keychain", "get", "protected"])
    assert result2.exit_code == 0


# ---------------------------------------------------------------------------
# empty value
# ---------------------------------------------------------------------------


def test_set_empty_value_exits_6(in_memory_keyring):
    """set with an empty --value exits with code 6 (INVALID_INPUT)."""
    result = runner.invoke(app, ["keychain", "set", "bad_ref", "--value", ""])
    assert result.exit_code == 6


# ---------------------------------------------------------------------------
# list (with mocked daemon HTTP client)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, body: dict) -> None:
        self._body = body
        self.status_code = 200

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._body


class _FakeClient:
    def __init__(self, resources: list[dict]) -> None:
        self._resources = resources

    def get(self, path: str, **_kwargs) -> _FakeResponse:
        return _FakeResponse({"resources": self._resources})

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *_: object) -> None:
        pass


def test_list_reports_refs_from_resources(in_memory_keyring, monkeypatch):
    """list enumerates credential refs from registered MCP server resources."""
    resources = [
        {
            "config": {
                "transport": {
                    "type": "http",
                    "credential_refs": {"Authorization": "gh_pat"},
                }
            }
        },
        {
            "config": {
                "transport": {
                    "type": "stdio",
                    "credential_refs": {"API_KEY": "openai_key"},
                }
            }
        },
    ]
    fake_info = DaemonInfo(
        version=1,
        pid=99,
        port=9999,
        token="t",
        started_at=dt.now(tz=UTC),
        binary_path="/fake",
    )
    fake_client = _FakeClient(resources)
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (fake_client, fake_info))

    # Set one of the refs so presence shows "yes"
    runner.invoke(app, ["keychain", "set", "gh_pat", "--value", "ghp_test"])

    result = runner.invoke(app, ["keychain", "list"])
    assert result.exit_code == 0
    assert "gh_pat" in result.output
    assert "openai_key" in result.output


def test_list_json(in_memory_keyring, monkeypatch):
    """list --json returns a JSON object with a sorted refs array."""
    resources = [
        {
            "config": {
                "transport": {
                    "credential_refs": {"KEY": "ref_b"},
                }
            }
        },
        {
            "config": {
                "transport": {
                    "credential_refs": {"TOKEN": "ref_a"},
                }
            }
        },
    ]
    fake_info = DaemonInfo(
        version=1, pid=1, port=9999, token="t", started_at=dt.now(tz=UTC), binary_path="/fake"
    )
    fake_client = _FakeClient(resources)
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (fake_client, fake_info))

    result = runner.invoke(app, ["keychain", "list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["refs"] == ["ref_a", "ref_b"]


def test_list_daemon_unreachable(in_memory_keyring, tmp_path, monkeypatch):
    """list when daemon is unreachable returns empty refs gracefully."""
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(app, ["keychain", "list"])
    assert result.exit_code == 0
    assert "daemon" in result.output.lower() or "no known" in result.output.lower()


# ---------------------------------------------------------------------------
# T2 — keychain list 5xx is rendered via check(), not bare raise_for_status()
# ---------------------------------------------------------------------------


_ERROR_BODY = (
    '{"error": {"code": "INTERNAL_ERROR", "message": "internal server error", "details": {}}}'
)


class _HttpErrorResponse:
    """Fake response that raises HTTPStatusError on raise_for_status()."""

    def __init__(self, status_code: int = 500) -> None:
        self.status_code = status_code
        self._real = httpx.Response(status_code, text=_ERROR_BODY)

    def raise_for_status(self) -> None:
        req = httpx.Request("GET", "http://fake/api/v1/resources")
        raise httpx.HTTPStatusError(
            f"Server error '{self.status_code}'",
            request=req,
            response=self._real,
        )

    def json(self) -> Any:
        return self._real.json()


class _HttpErrorClient:
    def get(self, *_args: Any, **_kwargs: Any) -> _HttpErrorResponse:
        return _HttpErrorResponse(500)

    def __enter__(self) -> _HttpErrorClient:
        return self

    def __exit__(self, *_: object) -> None:
        pass


def test_keychain_list_5xx_renders_message_exits_nonzero(in_memory_keyring, monkeypatch):
    """keychain list on a 5xx response must NOT raise a Traceback; must exit non-zero."""
    fake_info = DaemonInfo(
        version=1, pid=99, port=9999, token="t", started_at=dt.now(tz=UTC), binary_path="/fake"
    )
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (_HttpErrorClient(), fake_info))
    result = runner.invoke(app, ["keychain", "list"])
    assert result.exit_code != 0, "expected non-zero exit on 5xx"
    assert "Traceback" not in (result.output or ""), "Traceback leaked to output"
