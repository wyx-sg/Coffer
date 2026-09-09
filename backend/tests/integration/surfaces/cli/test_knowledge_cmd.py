"""Integration tests for the scope + entry half of `coffer knowledge ...`.

One command group replaces the former ``memory`` and ``kb`` groups, so the two
suites' scope-level verbs (`list` / `describe` / `create` / `configure` /
`delete`) are covered once here, alongside the entry verbs (`remember` /
`entries` / `get` / `edit-entry` / `forget` / `clear`), `recall` and
`organize`. The document verbs live in ``test_knowledge_document_cmd.py``.

We boot the full FastAPI app (via ``create_app``) so the knowledge kind is
wired with the production routes (real SQLite + real per-entry files under a
temp HOME), then route ``_cli_client.client_or_exit`` to a Starlette
``TestClient`` against that app. ``global`` and per-project scopes
auto-provision; a named collection is created with ``create``.
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
_TOKEN = "test-token-knowledge-cli"


def _extract_json(output: str) -> str:
    """Strip leading log lines so JSON can be decoded (alembic INFO logs get
    mingled with the CLI's stdout under CliRunner)."""
    lines = output.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line and line[0] in "[{":
            return "".join(lines[i:])
    return output


@pytest.fixture
def knowledge_cli_daemon(tmp_path, monkeypatch):
    """In-process daemon plumbed through the CLI client, real knowledge stack."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59800")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59809")
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))

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


def test_list_scopes_shows_global(knowledge_cli_daemon):
    result = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "list", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(_extract_json(result.output))
    assert any(s["name"] == "global" for s in data["scopes"])


def test_create_list_and_delete_named_collection(knowledge_cli_daemon):
    """A named collection is created and removed through the one group (was
    ``kb create`` / ``kb list`` / ``kb delete-kb``)."""
    created = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "create", "designs", "--description", "d"])
    assert created.exit_code == 0, created.output

    listed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "list", "--json"])
    assert listed.exit_code == 0, listed.output
    scopes = json.loads(_extract_json(listed.output))["scopes"]
    assert any(s["name"] == "designs" and s["scope"] == "named" for s in scopes)

    deleted = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "delete", "designs", "--yes"])
    assert deleted.exit_code == 0, deleted.output
    after = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "list", "--json"])
    assert all(s["name"] != "designs" for s in json.loads(_extract_json(after.output))["scopes"])


def test_remember_and_list_entries(knowledge_cli_daemon):
    added = _runner.invoke(
        cli_app, [KIND_KNOWLEDGE, "remember", "global", "prefers tabs", "--name", "tabs"]
    )
    assert added.exit_code == 0, added.output
    assert "added entry" in added.output

    listed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "entries", "global", "--json"])
    assert listed.exit_code == 0, listed.output
    data = json.loads(_extract_json(listed.output))
    assert data["total"] == 1
    assert data["entries"][0]["actor"] == "user"


def test_describe_scope(knowledge_cli_daemon):
    """One ``describe`` covers both former faces: the metrics payload is the
    union, so entries and documents are reported for every scope."""
    result = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "describe", "global", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(_extract_json(result.output))
    assert data["scope"]["name"] == "global"
    assert data["scope"]["scope"] == "global"
    assert "entry_count" in data["metrics"]
    assert "document_count" in data["metrics"]

    _runner.invoke(cli_app, [KIND_KNOWLEDGE, "create", "kb"])
    named = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "describe", "kb", "--json"])
    assert named.exit_code == 0, named.output
    named_data = json.loads(_extract_json(named.output))
    assert named_data["scope"]["name"] == "kb"
    assert named_data["scope"]["scope"] == "named"
    assert "document_count" in named_data["metrics"]


def test_get_edit_delete_entry(knowledge_cli_daemon):
    added = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "remember", "global", "old", "--name", "f"])
    assert added.exit_code == 0, added.output
    # Recover the id from an entries --json.
    listed = json.loads(
        _extract_json(
            _runner.invoke(cli_app, [KIND_KNOWLEDGE, "entries", "global", "--json"]).output
        )
    )
    eid = listed["entries"][0]["id"]

    got = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "get", "global", eid, "--json"])
    assert got.exit_code == 0, got.output

    edited = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "edit-entry", "global", eid, "new text"])
    assert edited.exit_code == 0, edited.output

    forgotten = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "forget", "global", eid])
    assert forgotten.exit_code == 0, forgotten.output


def test_clear_entries(knowledge_cli_daemon):
    _runner.invoke(cli_app, [KIND_KNOWLEDGE, "remember", "global", "a", "--name", "a"])
    _runner.invoke(cli_app, [KIND_KNOWLEDGE, "remember", "global", "b", "--name", "b"])
    cleared = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "clear", "global", "--yes"])
    assert cleared.exit_code == 0, cleared.output
    assert "cleared 2 entry" in cleared.output


def test_recall(knowledge_cli_daemon):
    _runner.invoke(
        cli_app, [KIND_KNOWLEDGE, "remember", "global", "the deploy command is make release"]
    )
    result = _runner.invoke(
        cli_app, [KIND_KNOWLEDGE, "recall", "global", "deploy command", "--json"]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(_extract_json(result.output))
    assert "hits" in data
    # One query → one answer: mode / fallback are no longer surfaced.
    assert "mode" not in data
    assert "fallback" not in data


def test_describe_missing_scope_exit_code_4(knowledge_cli_daemon):
    """Both a never-provisioned project scope and an unknown named collection
    exit 4 (was one test per former group)."""
    missing_project = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "describe", "project-NOPE"])
    assert missing_project.exit_code == 4, missing_project.output
    missing_named = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "describe", "ghost"])
    assert missing_named.exit_code == 4, missing_named.output


def test_configure_vector_and_chunking(knowledge_cli_daemon):
    """FR-017/FR-019: a scope's retrieval and chunking config is CLI-reachable
    (was ``memory configure`` + ``kb set-chunking``). Embedding is
    installation-wide, so no provider/model/dimension flags exist here."""
    r = _runner.invoke(
        cli_app,
        [
            KIND_KNOWLEDGE,
            "configure",
            "global",
            "--enable-vector",
            "--max-entry-chars",
            "4096",
            "--chunk-size",
            "128",
            "--chunk-overlap",
            "16",
        ],
    )
    assert r.exit_code == 0, r.output
    desc = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "describe", "global", "--json"])
    cfg = json.loads(_extract_json(desc.output))["scope"]["config"]
    assert "vector" in cfg["retrieval_modes"]
    assert cfg["max_entry_chars"] == 4096
    assert cfg["chunk_size"] == 128
    assert cfg["chunk_overlap"] == 16
    assert "embedding_provider" not in cfg
    assert "embedding" not in cfg


def test_configure_without_options_exits_nonzero(knowledge_cli_daemon):
    r = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "configure", "global"])
    assert r.exit_code != 0
    assert "nothing to configure" in r.output


def test_organize_no_model_noop(knowledge_cli_daemon):
    """`coffer knowledge organize` against a fresh install (no internal model)
    is a clean no-op — the CLI reports it and exits 0."""
    _runner.invoke(cli_app, [KIND_KNOWLEDGE, "remember", "global", "an entry"])
    result = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "organize", "global", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(_extract_json(result.output))
    assert data["status"] == "no_model"
    assert data["model"] is None
