"""Integration tests for `coffer knowledge ...` against the real stack.

We boot the full FastAPI app (via ``create_app``) so the knowledge kind is
wired with its production routes — real SQLite, real markdown files under a
temp HOME — then route ``_cli_client.client_or_exit`` at a Starlette
``TestClient`` over that app. Nothing auto-provisions any more: every
collection in here exists because a test created it (spec knowledge FR-010).
"""

from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime as dt

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.application.knowledge.service import KIND_KNOWLEDGE
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


def _ls(path: str) -> dict:
    result = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "ls", path, "--json"])
    assert result.exit_code == 0, result.output
    return json.loads(_extract_json(result.output))


def _make_collection(name: str, description: str = "test collection") -> None:
    created = _runner.invoke(
        cli_app, [KIND_KNOWLEDGE, "create", name, "--description", description]
    )
    assert created.exit_code == 0, created.output


@pytest.mark.acceptance(
    spec="knowledge", scenario="creating a collection registers a knowledge resource"
)
def test_create_registers_a_resource_and_lists_it(knowledge_cli_daemon):
    _make_collection("shopee", "Internal systems")

    listed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "collections", "--json"])
    assert listed.exit_code == 0, listed.output
    collections = json.loads(_extract_json(listed.output))["collections"]
    assert [c["name"] for c in collections] == ["shopee"]

    # The description a caller gave becomes the collection's README, so the
    # catalogue reads it back off disk rather than out of a row (FR-013).
    assert collections[0]["description"] == "Internal systems"


@pytest.mark.acceptance(
    spec="knowledge", scenario="the catalogue lists collections with their README description"
)
def test_catalogue_description_comes_from_the_readme(knowledge_cli_daemon, tmp_path):
    _make_collection("shopee", "First description")
    readme = tmp_path / "knowledge" / "shopee" / "README.md"
    readme.write_text("# shopee\n\nEdited by hand.\n", encoding="utf-8")

    listed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "collections", "--json"])
    collections = json.loads(_extract_json(listed.output))["collections"]
    assert collections[0]["description"] == "Edited by hand."


@pytest.mark.acceptance(
    spec="knowledge", scenario="a written note lands as a markdown file with a readable name"
)
def test_write_lands_as_a_readable_file(knowledge_cli_daemon, tmp_path):
    _make_collection("shopee")
    written = _runner.invoke(
        cli_app,
        [
            KIND_KNOWLEDGE,
            "write",
            "--title",
            "Account Gateway",
            "--description",
            "Where account decisions are made",
            "--body",
            "The orchestration layer.",
            "--in",
            "shopee",
        ],
    )
    assert written.exit_code == 0, written.output
    assert (tmp_path / "knowledge" / "shopee" / "account-gateway.md").is_file()


@pytest.mark.acceptance(spec="knowledge", scenario="read returns a file by path")
def test_read_returns_the_body(knowledge_cli_daemon):
    _make_collection("shopee")
    _runner.invoke(
        cli_app,
        [
            KIND_KNOWLEDGE,
            "write",
            "--title",
            "Session",
            "--description",
            "d",
            "--body",
            "account.session owns login state",
            "--in",
            "shopee",
        ],
    )
    read = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "read", "shopee/session.md"])
    assert read.exit_code == 0, read.output
    assert "account.session owns login state" in read.output


@pytest.mark.acceptance(spec="knowledge", scenario="grep matches CJK content")
def test_grep_matches_cjk_without_a_tokenizer(knowledge_cli_daemon):
    _make_collection("shopee")
    _runner.invoke(
        cli_app,
        [
            KIND_KNOWLEDGE,
            "write",
            "--title",
            "Session",
            "--description",
            "登录态",
            "--body",
            "account.session 负责登录态 token",
            "--in",
            "shopee",
        ],
    )
    found = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "grep", "登录态", "--json"])
    assert found.exit_code == 0, found.output
    matches = json.loads(_extract_json(found.output))["matches"]
    assert any(m["path"] == "shopee/session.md" for m in matches)


@pytest.mark.acceptance(spec="knowledge", scenario="delete removes the file from disk")
def test_delete_removes_the_file(knowledge_cli_daemon, tmp_path):
    _make_collection("shopee")
    _runner.invoke(
        cli_app,
        [
            KIND_KNOWLEDGE,
            "write",
            "--title",
            "Stale",
            "--description",
            "d",
            "--body",
            "b",
            "--in",
            "shopee",
        ],
    )
    path = tmp_path / "knowledge" / "shopee" / "stale.md"
    assert path.is_file()

    removed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "delete", "shopee/stale.md"])
    assert removed.exit_code == 0, removed.output
    assert not path.exists()


@pytest.mark.acceptance(
    spec="knowledge", scenario="an unknown collection is an error, never auto-created"
)
def test_unknown_collection_is_an_error(knowledge_cli_daemon, tmp_path):
    result = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "ls", "typo", "--json"])
    assert result.exit_code != 0
    assert not (tmp_path / "knowledge" / "typo").exists()


def test_write_needs_exactly_one_target(knowledge_cli_daemon):
    result = _runner.invoke(
        cli_app,
        [
            KIND_KNOWLEDGE,
            "write",
            "--title",
            "t",
            "--description",
            "d",
            "--in",
            "shopee",
            "--path",
            "shopee/t.md",
        ],
    )
    assert result.exit_code == 2
