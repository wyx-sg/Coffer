"""Integration tests for the document half of `coffer knowledge ...`.

Every document verb (`ingest` / `documents` / `read` / `edit` / `reconvert` /
`reindex` / `search` / `grep` / `delete-doc`) plus the ``--json`` switch where
it exists. The scope-level verbs these build on (`create` / `describe` /
`configure` / `delete`) are covered in ``test_knowledge_cmd.py``.

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
from coffer.domain.knowledge.document import KIND_KNOWLEDGE
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_runner = CliRunner()
_TOKEN = "test-token-knowledge-doc-cli"


def _extract_json(output: str) -> str:
    lines = output.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line and line[0] in "[{":
            return "".join(lines[i:])
    return output


@pytest.fixture
def knowledge_doc_cli_daemon(tmp_path, monkeypatch):
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


def test_ingest_list_read_edit_reindex_search_grep_delete(knowledge_doc_cli_daemon, tmp_path):
    _runner.invoke(cli_app, [KIND_KNOWLEDGE, "create", "kb"])
    doc = tmp_path / "notes.md"
    doc.write_text("# Title\n\ndeploy via make release\n", encoding="utf-8")

    ing = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "ingest", "kb", str(doc)])
    assert ing.exit_code == 0, ing.output

    listed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "documents", "kb", "--json"])
    assert listed.exit_code == 0, listed.output
    docs = json.loads(_extract_json(listed.output))["documents"]
    assert len(docs) == 1
    doc_id = docs[0]["id"]

    got = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "read", "kb", doc_id])
    assert got.exit_code == 0, got.output
    assert "make release" in got.output

    edited = _runner.invoke(
        cli_app, [KIND_KNOWLEDGE, "edit", "kb", doc_id, "# Edited\n\nmake ship now\n"]
    )
    assert edited.exit_code == 0, edited.output

    reindexed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "reindex", "kb"])
    assert reindexed.exit_code == 0, reindexed.output

    searched = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "search", "kb", "make ship", "--json"])
    assert searched.exit_code == 0, searched.output
    assert "passages" in json.loads(_extract_json(searched.output))

    grepped = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "grep", "kb", "make ship", "--json"])
    assert grepped.exit_code == 0, grepped.output
    assert "hits" in json.loads(_extract_json(grepped.output))

    deleted = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "delete-doc", "kb", doc_id])
    assert deleted.exit_code == 0, deleted.output


def test_ingest_into_auto_scope_and_read_body(knowledge_doc_cli_daemon, tmp_path):
    """Documents are not a named-collection privilege any more: the merged kind
    ingests into ``global`` too, and ``read`` prints the markdown body."""
    doc_file = tmp_path / "body.md"
    doc_file.write_text("# Body\n\nhello from knowledge read\n", encoding="utf-8")
    ing = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "ingest", "global", str(doc_file)])
    assert ing.exit_code == 0, ing.output
    doc_id = ing.output.split("id=")[1].split(" ")[0]

    out = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "read", "global", doc_id])
    assert out.exit_code == 0, out.output
    assert "hello from knowledge read" in out.output

    desc = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "describe", "global", "--json"])
    assert json.loads(_extract_json(desc.output))["metrics"]["document_count"] == 1


def test_reconvert(knowledge_doc_cli_daemon, tmp_path):
    """``reconvert`` has a CLI verb and re-runs conversion from the original."""
    _runner.invoke(cli_app, [KIND_KNOWLEDGE, "create", "kb1"])
    doc_file = tmp_path / "re.md"
    doc_file.write_text("# Re\n\nreconvertible body\n", encoding="utf-8")
    ing = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "ingest", "kb1", str(doc_file)])
    assert ing.exit_code == 0, ing.output
    doc_id = ing.output.split("id=")[1].split(" ")[0]

    rc = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "reconvert", "kb1", doc_id])
    assert rc.exit_code == 0, rc.output


def test_check_sources_reports_tracked_original(knowledge_doc_cli_daemon, tmp_path):
    """The CLI records the ingested file's absolute path, so ``check-sources``
    can report on it."""
    _runner.invoke(cli_app, [KIND_KNOWLEDGE, "create", "kb2"])
    doc_file = tmp_path / "tracked.md"
    doc_file.write_text("# Tracked\n\noriginal body\n", encoding="utf-8")
    ing = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "ingest", "kb2", str(doc_file)])
    assert ing.exit_code == 0, ing.output

    checked = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "check-sources", "kb2", "--json"])
    assert checked.exit_code == 0, checked.output
    sources = json.loads(_extract_json(checked.output))["sources"]
    assert [s["source_path"] for s in sources] == [str(doc_file.resolve())]
