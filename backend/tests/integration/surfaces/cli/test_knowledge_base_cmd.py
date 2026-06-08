"""Integration tests for `coffer kb ...` CLI subcommands (spec 006 redesign).

Every verb (`create` / `list` / `describe` / `ingest` / `list-docs` /
`get-doc` / `edit` / `reindex` / `search` / `grep` / `delete-doc` /
`delete-kb`) plus the ``--json`` switch where it exists.

Boots the full FastAPI app (real SQLite + real files under a temp HOME) and
routes ``_cli_client.client_or_exit`` to a Starlette ``TestClient``. Markdown
passthrough means no heavy converter/embedder is booted.
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
_TOKEN = "test-token-kb-cli"


def _extract_json(output: str) -> str:
    lines = output.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line and line[0] in "[{":
            return "".join(lines[i:])
    return output


@pytest.fixture
def kb_cli_daemon(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59840")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59849")
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))

    app = create_app()
    set_active_token(_TOKEN)
    info = DaemonInfo(
        version=1,
        pid=12345,
        port=59840,
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


def test_create_and_list_kb(kb_cli_daemon):
    created = _runner.invoke(cli_app, ["kb", "create", "designs", "--description", "d"])
    assert created.exit_code == 0, created.output
    listed = _runner.invoke(cli_app, ["kb", "list", "--json"])
    assert listed.exit_code == 0, listed.output
    data = json.loads(_extract_json(listed.output))
    assert any(k["name"] == "designs" for k in data["knowledge_bases"])


def test_describe_kb(kb_cli_daemon):
    _runner.invoke(cli_app, ["kb", "create", "kb"])
    result = _runner.invoke(cli_app, ["kb", "describe", "kb", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(_extract_json(result.output))
    assert data["knowledge_base"]["name"] == "kb"
    assert "document_count" in data["metrics"]


def test_ingest_list_get_edit_reindex_search_grep_delete(kb_cli_daemon, tmp_path):
    _runner.invoke(cli_app, ["kb", "create", "kb"])
    doc = tmp_path / "notes.md"
    doc.write_text("# Title\n\ndeploy via make release\n", encoding="utf-8")

    ing = _runner.invoke(cli_app, ["kb", "ingest", "kb", str(doc)])
    assert ing.exit_code == 0, ing.output

    listed = _runner.invoke(cli_app, ["kb", "list-docs", "kb", "--json"])
    assert listed.exit_code == 0, listed.output
    docs = json.loads(_extract_json(listed.output))["documents"]
    assert len(docs) == 1
    doc_id = docs[0]["id"]

    got = _runner.invoke(cli_app, ["kb", "get-doc", "kb", doc_id])
    assert got.exit_code == 0, got.output
    assert "make release" in got.output

    edited = _runner.invoke(cli_app, ["kb", "edit", "kb", doc_id, "# Edited\n\nmake ship now\n"])
    assert edited.exit_code == 0, edited.output

    reindexed = _runner.invoke(cli_app, ["kb", "reindex", "kb"])
    assert reindexed.exit_code == 0, reindexed.output

    searched = _runner.invoke(cli_app, ["kb", "search", "kb", "make ship", "--json"])
    assert searched.exit_code == 0, searched.output
    assert "passages" in json.loads(_extract_json(searched.output))

    grepped = _runner.invoke(cli_app, ["kb", "grep", "kb", "make ship", "--json"])
    assert grepped.exit_code == 0, grepped.output
    assert "hits" in json.loads(_extract_json(grepped.output))

    deleted = _runner.invoke(cli_app, ["kb", "delete-doc", "kb", doc_id])
    assert deleted.exit_code == 0, deleted.output


def test_describe_missing_kb_exit_code_4(kb_cli_daemon):
    result = _runner.invoke(cli_app, ["kb", "describe", "ghost"])
    assert result.exit_code == 4, result.output


def test_delete_kb(kb_cli_daemon):
    _runner.invoke(cli_app, ["kb", "create", "kb"])
    result = _runner.invoke(cli_app, ["kb", "delete-kb", "kb", "--yes"])
    assert result.exit_code == 0, result.output
    listed = json.loads(_extract_json(_runner.invoke(cli_app, ["kb", "list", "--json"]).output))
    assert all(k["name"] != "kb" for k in listed["knowledge_bases"])
