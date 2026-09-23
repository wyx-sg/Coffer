"""Integration tests for `coffer knowledge ...` against the real stack.

We boot the full FastAPI app (via ``create_app``) so the knowledge kind is
wired with its production routes — real SQLite, real markdown files under a
temp HOME — then route ``_cli_client.client_or_exit`` at a Starlette
``TestClient`` over that app. Nothing auto-provisions any more: every
collection in here exists because a test created it (spec knowledge "Create
collections only deliberately").

The group covers exactly the list in "Cover collection management on REST and
the CLI" and nothing beyond it. There is no ``grep`` and no ``search`` command
any more: the corpus is plain Markdown under ``~/.coffer/knowledge/``, so a
person's own ``grep`` is better than anything this group could wrap — and the
tests that drove those two commands are gone with them rather than softened into
asserting a different command.
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


def _make_collection(name: str, description: str = "test collection") -> None:
    created = _runner.invoke(
        cli_app, [KIND_KNOWLEDGE, "create", name, "--description", description]
    )
    assert created.exit_code == 0, created.output


def _write(collection: str, title: str, body: str = "b", description: str = "d") -> str:
    """Submit one piece of material and return the line the command printed.

    The command takes ``--in <collection>`` and never a path: where knowledge
    lands is the layer's call (spec knowledge "Submit every entrance's input as
    material"). The app booted here has no internal model, so the material is
    promoted to a document on the spot and the line is that document's path
    ("Promote material directly when no model is configured").
    """
    written = _runner.invoke(
        cli_app,
        [
            KIND_KNOWLEDGE,
            "write",
            "--title",
            title,
            "--description",
            description,
            "--body",
            body,
            "--in",
            collection,
        ],
    )
    assert written.exit_code == 0, written.output
    return written.output.strip().splitlines()[-1]


def _document(tmp_path, relpath: str, body: str) -> None:  # type: ignore[no-untyped-def]
    """A document written straight into the tree, as a person's editor would."""
    path = tmp_path / "knowledge" / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\ntitle: Derived\ndescription: d\nactor: agent\n"
        "created_at: '2026-09-17T00:00:00+00:00'\nupdated_at: '2026-09-17T00:00:00+00:00'\n"
        f"---\n\n{body}\n",
        encoding="utf-8",
    )


# ----- collections ---------------------------------------------------------


def test_create_registers_a_collection_and_lists_it(knowledge_cli_daemon, tmp_path):
    _make_collection("shopee", "Internal systems")

    collection = tmp_path / "knowledge" / "shopee"
    assert collection.is_dir()
    assert not (collection / "sources").exists() and not (collection / "topics").exists()

    listed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "collections", "--json"])
    assert listed.exit_code == 0, listed.output
    collections = json.loads(_extract_json(listed.output))["collections"]
    assert [c["name"] for c in collections] == ["shopee"]
    assert collections[0]["description"] == "Internal systems"
    # Documents an agent can read, and material still waiting to be merged
    # into them — the second is what an agent cannot see yet ("Hide dot-prefixed
    # entries except the inbox").
    assert (collections[0]["document_count"], collections[0]["pending_count"]) == (0, 0)


@pytest.mark.acceptance(
    spec="knowledge", scenario="the catalogue lists collections with their README description"
)
def test_catalogue_description_comes_from_the_readme(knowledge_cli_daemon, tmp_path):
    _make_collection("shopee", "First description")
    readme = tmp_path / "knowledge" / "shopee" / "README.md"
    readme.write_text("# shopee\n\nEdited by hand.\n", encoding="utf-8")

    listed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "collections", "--json"])
    collections = json.loads(_extract_json(listed.output))["collections"]
    # Read off disk on every listing, never out of a row ("Read a collection's
    # description from its README") — so the
    # string the creation call supplied is not what comes back.
    assert collections[0]["description"] == "Edited by hand."


def test_collections_renders_a_table_without_json(knowledge_cli_daemon):
    _make_collection("shopee", "Internal systems")
    listed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "collections"])
    assert listed.exit_code == 0, listed.output
    assert "shopee" in listed.output


# ----- writing and reading -------------------------------------------------


def test_write_becomes_a_document_under_a_readable_name(knowledge_cli_daemon, tmp_path):
    _make_collection("shopee")

    path = _write("shopee", "Account Gateway", body="The orchestration layer.")

    assert path == "shopee/account-gateway.md"
    assert (tmp_path / "knowledge" / path).is_file()


def test_write_says_when_the_material_is_queued(knowledge_cli_daemon, tmp_path, monkeypatch):
    """With a model to merge it, material waits in the inbox and there is no
    document path to print — the command says it was queued instead."""
    from coffer.surfaces.http.knowledge.dependencies import get_knowledge_service

    async def _yes() -> bool:
        return True

    monkeypatch.setattr(get_knowledge_service(), "_merge_available", _yes)
    _make_collection("shopee")

    line = _write("shopee", "Gateway")

    assert line.startswith("queued in shopee")
    assert [p.name for p in (tmp_path / "knowledge" / "shopee" / ".inbox").iterdir()] == [
        "gateway.md"
    ]


def test_write_takes_no_folder(knowledge_cli_daemon):
    """Where material lands is curation's call ("Submit every entrance's input as
    material"): there is no
    ``--folder`` and no ``--path`` to aim it."""
    _make_collection("shopee")
    for flag, value in (("--folder", "apis"), ("--path", "shopee/t.md")):
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
                flag,
                value,
            ],
        )
        assert result.exit_code == 2, result.output


def test_read_returns_the_body_of_any_document(knowledge_cli_daemon, tmp_path):
    _make_collection("shopee")
    path = _write("shopee", "Session", body="account.session owns login state")

    read = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "read", path])
    assert read.exit_code == 0, read.output
    assert "account.session owns login state" in read.output

    # A document curation wrote, in a folder, reads exactly the same way.
    _document(tmp_path, "shopee/apis/derived.md", "what curation concluded")
    read_nested = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "read", "shopee/apis/derived.md"])
    assert read_nested.exit_code == 0, read_nested.output
    assert "what curation concluded" in read_nested.output


def test_ls_lists_one_level_of_a_collection(knowledge_cli_daemon, tmp_path):
    _make_collection("shopee")
    path = _write("shopee", "Session")
    _document(tmp_path, "shopee/apis/gateway.md", "b")

    listed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "ls", "shopee", "--json"])
    assert listed.exit_code == 0, listed.output
    data = json.loads(_extract_json(listed.output))
    assert [f["path"] for f in data["files"]] == [path]
    assert [d["path"] for d in data["directories"]] == ["shopee/apis"]

    nested = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "ls", "shopee/apis", "--json"])
    assert [f["path"] for f in json.loads(_extract_json(nested.output))["files"]] == [
        "shopee/apis/gateway.md"
    ]


@pytest.mark.acceptance(
    spec="knowledge", scenario="an unknown collection is an error, never auto-created"
)
def test_unknown_collection_is_an_error(knowledge_cli_daemon, tmp_path):
    result = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "ls", "typo", "--json"])
    assert result.exit_code != 0
    assert not (tmp_path / "knowledge" / "typo").exists()


# ----- deleting ------------------------------------------------------------


def test_delete_removes_a_source_from_disk(knowledge_cli_daemon, tmp_path):
    _make_collection("shopee")
    path = _write("shopee", "Stale")
    on_disk = tmp_path / "knowledge" / path
    assert on_disk.is_file()

    removed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "delete", path])
    assert removed.exit_code == 0, removed.output
    assert not on_disk.exists()


def test_delete_removes_a_document_curation_wrote(knowledge_cli_daemon, tmp_path):
    """The collection is the person's as much as curation's.

    See "Let only a person delete a document".
    """
    _make_collection("shopee")
    _document(tmp_path, "shopee/derived.md", "b")

    removed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "delete", "shopee/derived.md"])
    assert removed.exit_code == 0, removed.output
    assert not (tmp_path / "knowledge" / "shopee" / "derived.md").exists()


def test_delete_refuses_the_readme(knowledge_cli_daemon, tmp_path):
    """The README describes the collection rather than being a document in it."""
    _make_collection("shopee")

    removed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "delete", "shopee/README.md"])
    assert removed.exit_code != 0
    assert (tmp_path / "knowledge" / "shopee" / "README.md").is_file()


# ----- upload and curate ---------------------------------------------------


def test_cli_upload_becomes_one_document_and_keeps_no_original(knowledge_cli_daemon, tmp_path):
    _make_collection("shopee")
    # A CSV, so the conversion genuinely differs from the bytes uploaded.
    source = tmp_path / "team.csv"
    source.write_bytes(b"name,owner\nsession,account\n")

    result = _runner.invoke(
        cli_app,
        [KIND_KNOWLEDGE, "upload", str(source), "--collection", "shopee"],
    )
    assert result.exit_code == 0, result.output
    # The Markdown is named for the document's own title, not for the file it
    # arrived as ("Use the file path as a document's identity").
    path = result.output.strip().splitlines()[-1]
    assert path == "shopee/team.md"
    assert (tmp_path / "knowledge" / path).is_file()
    # The original is not kept: the collection holds knowledge, not the
    # documents it arrived in ("Convert uploads into material without keeping
    # them").
    collection = tmp_path / "knowledge" / "shopee"
    assert sorted(str(p.relative_to(collection)) for p in collection.rglob("*") if p.is_file()) == [
        "README.md",
        "team.md",
    ]


def test_cli_upload_of_unsupported_type_is_refused(knowledge_cli_daemon, tmp_path):
    _make_collection("shopee")
    source = tmp_path / "binary.exe"
    source.write_bytes(b"\x00\x01\x02")

    result = _runner.invoke(
        cli_app,
        [KIND_KNOWLEDGE, "upload", str(source), "--collection", "shopee"],
    )
    assert result.exit_code != 0, result.output


def test_cli_curate_reports_why_a_pass_did_nothing(knowledge_cli_daemon):
    """Per "Promote material directly when no model is configured": with no
    internal connection configured a pass is a clean no-op, and the status IS
    the answer — not an error the CLI has to invent."""
    _make_collection("shopee")
    _write("shopee", "Session")

    result = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "curate", "shopee"])
    assert result.exit_code == 0, result.output
    outcome = json.loads(_extract_json(result.output))
    assert outcome["status"] == "no_model"
    assert outcome["collection"] == "shopee"
    # The material was already promoted when it arrived, so nothing was left.
    assert outcome["promoted"] == []


def test_cli_curate_takes_one_document(knowledge_cli_daemon):
    """``--document`` carries one edited document through; with no model the
    answer is still the honest ``no_model``, not an error."""
    _make_collection("shopee")
    path = _write("shopee", "Session")

    result = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "curate", "shopee", "--document", path])
    assert result.exit_code == 0, result.output
    assert json.loads(_extract_json(result.output))["status"] == "no_model"


def test_cli_curate_on_an_unknown_collection_is_an_error(knowledge_cli_daemon):
    result = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "curate", "typo"])
    assert result.exit_code != 0


# ----- spec scenarios added with the OpenSpec rewrite ----------------------


def _daemon() -> TestClient:
    """The in-process daemon the fixture plumbed behind the CLI."""
    client, _ = _cli_client.client_or_exit()
    return client  # type: ignore[return-value]


def _hold_material(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Report an internal model as configured, so material waits to be merged."""
    from coffer.surfaces.http.knowledge.dependencies import get_knowledge_service

    async def _yes() -> bool:
        return True

    monkeypatch.setattr(get_knowledge_service(), "_merge_available", _yes)


@pytest.mark.acceptance(
    spec="knowledge", scenario="the CLI and the material route leave material in the inbox"
)
def test_cli_and_route_both_leave_material_in_the_inbox(
    knowledge_cli_daemon, tmp_path, monkeypatch
):
    _make_collection("shopee")
    _hold_material(monkeypatch)

    line = _write("shopee", "From the CLI")
    assert line.startswith("queued in shopee")

    resp = _daemon().post(
        "/knowledge/material",
        json={"collection": "shopee", "title": "From the route", "description": "d", "body": "b"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "pending"
    assert resp.json()["path"] is None

    collection = tmp_path / "knowledge" / "shopee"
    assert sorted(p.name for p in (collection / ".inbox").iterdir()) == [
        "from-the-cli.md",
        "from-the-route.md",
    ]
    visible = [
        p for p in collection.rglob("*.md") if ".inbox" not in p.parts and p.name != "README.md"
    ]
    assert visible == []


@pytest.mark.acceptance(spec="knowledge", scenario="delete a document an agent wrote")
def test_a_person_deletes_agent_written_documents_on_both_surfaces(knowledge_cli_daemon, tmp_path):
    _make_collection("shopee")
    _document(tmp_path, "shopee/by-route.md", "b")
    _document(tmp_path, "shopee/by-cli.md", "b")
    for name in ("by-route.md", "by-cli.md"):
        assert "actor: agent" in (tmp_path / "knowledge" / "shopee" / name).read_text()

    resp = _daemon().delete("/knowledge/file", params={"path": "shopee/by-route.md"})
    assert resp.status_code == 204, resp.text
    removed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "delete", "shopee/by-cli.md"])
    assert removed.exit_code == 0, removed.output

    assert not (tmp_path / "knowledge" / "shopee" / "by-route.md").exists()
    assert not (tmp_path / "knowledge" / "shopee" / "by-cli.md").exists()
    audit = _daemon().get("/audit", params={"event_type": "knowledge_deleted"})
    assert audit.status_code == 200, audit.text
    deleted = sorted(e["details"]["path"] for e in audit.json()["entries"])
    assert deleted == ["shopee/by-cli.md", "shopee/by-route.md"]


_KNOWLEDGE_OPERATIONS = {
    ("POST", "/api/v1/knowledge/collections"),
    ("GET", "/api/v1/knowledge/tree"),
    ("GET", "/api/v1/knowledge/file"),
    ("POST", "/api/v1/knowledge/material"),
    ("POST", "/api/v1/knowledge/upload"),
    ("DELETE", "/api/v1/knowledge/file"),
    ("POST", "/api/v1/knowledge/collections/{uid}/curate"),
}
_KNOWLEDGE_COMMANDS = {"create", "ls", "read", "write", "upload", "delete", "curate"}
_FORBIDDEN_ROUTE_WORDS = ("index", "reindex", "source", "embedding", "scope", "reach")


@pytest.mark.acceptance(
    spec="knowledge", scenario="expose every collection operation and no document write"
)
def test_rest_and_cli_cover_every_operation_and_write_no_document(knowledge_cli_daemon):
    from coffer.surfaces.cli.knowledge_cmd import app as knowledge_app

    # Read from the OpenAPI schema: FastAPI 0.141 no longer flattens an included
    # router's routes into ``app.routes``, so walking that list finds nothing.
    schema = _daemon()._inner.app.openapi()  # type: ignore[attr-defined]
    routes = {
        (method.upper(), path)
        for path, operations in (schema.get("paths") or {}).items()
        if path.startswith("/api/v1/knowledge")
        for method in operations
    }
    assert routes >= _KNOWLEDGE_OPERATIONS

    commands = {command.name for command in knowledge_app.registered_commands}
    assert commands >= _KNOWLEDGE_COMMANDS

    assert not any(method in {"PUT", "PATCH"} for method, _ in routes)
    for _, path in routes:
        tail = path.removeprefix("/api/v1/knowledge").lower()
        assert not any(word in tail for word in _FORBIDDEN_ROUTE_WORDS), path
