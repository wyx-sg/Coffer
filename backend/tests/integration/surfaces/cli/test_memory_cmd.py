"""Integration tests for `coffer memory ...` CLI subcommands (spec 007 redesign).

Every verb (`list` / `describe` / `add` / `list` / `get` / `edit` / `delete` /
`clear` / `recall`) plus the ``--json``
switch where it exists. No LLM-provider flags and no 503 path.

We boot the full FastAPI app (via ``create_app``) so the memory kind is wired
with the production routes (real SQLite + real per-fact files under a temp
HOME), then route ``_cli_client.client_or_exit`` to a Starlette ``TestClient``
against that app. Stores auto-provision per scope.
"""

from __future__ import annotations

import json
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
_TOKEN = "test-token-memory-cli"


def _extract_json(output: str) -> str:
    """Strip leading log lines so JSON can be decoded (alembic INFO logs get
    mingled with the CLI's stdout under CliRunner)."""
    lines = output.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line and line[0] in "[{":
            return "".join(lines[i:])
    return output


@pytest.fixture
def memory_cli_daemon(tmp_path, monkeypatch):
    """In-process daemon plumbed through the CLI client, real memory stack."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59800")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59809")
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(tmp_path / "memory"))

    app = create_app()
    set_active_token(_TOKEN)

    info = DaemonInfo(
        version=1,
        pid=12345,
        port=59800,
        token=_TOKEN,
        started_at=dt.now(tz=UTC),
        binary_path="/test",
    )

    fake_client = TestClient(
        app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "cli"},
        raise_server_exceptions=False,
    )
    fake_client.__enter__()

    class _PersistentClient:
        def __init__(self, inner: TestClient) -> None:
            self._inner = inner

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return None

        def __getattr__(self, item):  # type: ignore[no-untyped-def]
            return getattr(self._inner, item)

    monkeypatch.setattr(
        _cli_client,
        "client_or_exit",
        lambda: (_PersistentClient(fake_client), info),
    )
    yield
    fake_client.__exit__(None, None, None)


def test_list_stores_shows_global(memory_cli_daemon):
    result = _runner.invoke(cli_app, ["memory", "list", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(_extract_json(result.output))
    assert any(s["name"] == "global" for s in data["memory_stores"])


def test_add_and_list_facts(memory_cli_daemon):
    add = _runner.invoke(cli_app, ["memory", "add", "global", "prefers tabs", "--name", "tabs"])
    assert add.exit_code == 0, add.output
    assert "added fact" in add.output

    listed = _runner.invoke(cli_app, ["memory", "facts", "global", "--json"])
    assert listed.exit_code == 0, listed.output
    data = json.loads(_extract_json(listed.output))
    assert data["total"] == 1
    assert data["facts"][0]["actor"] == "user"


def test_describe_store(memory_cli_daemon):
    result = _runner.invoke(cli_app, ["memory", "describe", "global", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(_extract_json(result.output))
    assert data["memory_store"]["scope"] == "global"
    assert "fact_count" in data["metrics"]


def test_get_edit_delete_fact(memory_cli_daemon):
    add = _runner.invoke(cli_app, ["memory", "add", "global", "old", "--name", "f"])
    assert add.exit_code == 0, add.output
    # Recover the id from a list --json.
    listed = json.loads(
        _extract_json(_runner.invoke(cli_app, ["memory", "facts", "global", "--json"]).output)
    )
    fid = listed["facts"][0]["id"]

    got = _runner.invoke(cli_app, ["memory", "get", "global", fid, "--json"])
    assert got.exit_code == 0, got.output

    edited = _runner.invoke(cli_app, ["memory", "edit", "global", fid, "new text"])
    assert edited.exit_code == 0, edited.output

    deleted = _runner.invoke(cli_app, ["memory", "delete", "global", fid])
    assert deleted.exit_code == 0, deleted.output


def test_clear_facts(memory_cli_daemon):
    _runner.invoke(cli_app, ["memory", "add", "global", "a", "--name", "a"])
    _runner.invoke(cli_app, ["memory", "add", "global", "b", "--name", "b"])
    cleared = _runner.invoke(cli_app, ["memory", "clear", "global", "--yes"])
    assert cleared.exit_code == 0, cleared.output
    assert "cleared 2 fact" in cleared.output


def test_recall(memory_cli_daemon):
    _runner.invoke(cli_app, ["memory", "add", "global", "the deploy command is make release"])
    result = _runner.invoke(cli_app, ["memory", "recall", "global", "deploy command", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(_extract_json(result.output))
    assert "hits" in data
    assert "mode" in data


def test_describe_missing_store_exit_code_4(memory_cli_daemon):
    result = _runner.invoke(cli_app, ["memory", "describe", "project-NOPE"])
    assert result.exit_code == 4, result.output


def test_memory_configure_enables_vector(memory_cli_daemon):
    """FR-017/FR-019: store config (incl. vector enablement) is CLI-reachable."""
    r = _runner.invoke(
        cli_app,
        [
            "memory",
            "configure",
            "global",
            "--provider",
            "local",
            "--model",
            "bge-m3",
            "--dimensions",
            "32",
            "--enable-vector",
        ],
    )
    assert r.exit_code == 0, r.output
    desc = _runner.invoke(cli_app, ["memory", "describe", "global", "--json"])
    cfg = json.loads(_extract_json(desc.output))["memory_store"]["config"]
    assert cfg["embedding_provider"] == "local"
    assert cfg["embedding_dimensions"] == 32
    assert "vector" in cfg["retrieval_modes"]
