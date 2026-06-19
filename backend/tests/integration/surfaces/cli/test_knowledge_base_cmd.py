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


def test_kb_set_embedding_and_read_alias(kb_cli_daemon, tmp_path):
    """FR-019/FR-014: vector enablement is reachable from the CLI, and ``read``
    aliases ``get-doc`` (the quickstart's documented verb)."""
    r = _runner.invoke(cli_app, ["kb", "create", "kb1"])
    assert r.exit_code == 0, r.output
    r = _runner.invoke(
        cli_app,
        [
            "kb",
            "set-embedding",
            "kb1",
            "--provider",
            "local",
            "--model",
            "bge-m3",
            "--dimensions",
            "32",
        ],
    )
    assert r.exit_code == 0, r.output
    desc = _runner.invoke(cli_app, ["kb", "describe", "kb1", "--json"])
    cfg = json.loads(_extract_json(desc.output))["knowledge_base"]["config"]
    assert cfg["embedding"]["provider"] == "local"
    assert cfg["embedding"]["dimensions"] == 32
    assert "vector" in cfg["enabled_modes"]

    # read == get-doc
    doc_file = tmp_path / "alias.md"
    doc_file.write_text("# Alias\n\nhello from read alias\n", encoding="utf-8")
    ing = _runner.invoke(cli_app, ["kb", "ingest", "kb1", str(doc_file)])
    assert ing.exit_code == 0, ing.output
    doc_id = ing.output.split("id=")[1].split(" ")[0]
    out = _runner.invoke(cli_app, ["kb", "read", "kb1", doc_id])
    assert out.exit_code == 0, out.output
    assert "hello from read alias" in out.output


def test_kb_set_chunking_and_reconvert(kb_cli_daemon, tmp_path):
    """Chunk params are CLI-mutable and reconvert has a CLI verb."""
    _runner.invoke(cli_app, ["kb", "create", "kb1"])
    r = _runner.invoke(
        cli_app, ["kb", "set-chunking", "kb1", "--chunk-size", "128", "--chunk-overlap", "16"]
    )
    assert r.exit_code == 0, r.output
    desc = _runner.invoke(cli_app, ["kb", "describe", "kb1", "--json"])
    cfg = json.loads(_extract_json(desc.output))["knowledge_base"]["config"]
    assert cfg["chunk_size"] == 128
    assert cfg["chunk_overlap"] == 16

    doc_file = tmp_path / "re.md"
    doc_file.write_text("# Re\n\nreconvertible body\n", encoding="utf-8")
    ing = _runner.invoke(cli_app, ["kb", "ingest", "kb1", str(doc_file)])
    doc_id = ing.output.split("id=")[1].split(" ")[0]
    rc = _runner.invoke(cli_app, ["kb", "reconvert", "kb1", doc_id])
    assert rc.exit_code == 0, rc.output


def test_trash_restore_and_project_scope_cli(kb_cli_daemon, tmp_path):
    """`kb ingest --project-id`, then delete-doc -> `kb trash` -> `kb restore`
    round-trips the recoverable soft-delete over the real CLI (ADR-030)."""
    _runner.invoke(cli_app, ["kb", "create", "kb"])
    doc = tmp_path / "a.md"
    doc.write_text("# A\n\ngrape soda")
    proj = "0123456789ABCDEFGHJKMNPQRS"  # a valid 26-char Crockford ULID
    ing = _runner.invoke(cli_app, ["kb", "ingest", "kb", str(doc), "--project-id", proj])
    assert ing.exit_code == 0, ing.output
    doc_id = ing.output.split("id=")[1].split(" ")[0].strip()
    # the project-scoped list shows it
    plist = _runner.invoke(cli_app, ["kb", "list-docs", "kb", "--project-id", proj, "--json"])
    assert plist.exit_code == 0 and doc_id in plist.output
    # delete -> trash, then restore
    assert _runner.invoke(cli_app, ["kb", "delete-doc", "kb", doc_id]).exit_code == 0
    trash = _runner.invoke(cli_app, ["kb", "trash", "kb", "--json"])
    assert trash.exit_code == 0 and doc_id in trash.output
    rs = _runner.invoke(cli_app, ["kb", "restore", "kb", doc_id])
    assert rs.exit_code == 0 and "restored" in rs.output
