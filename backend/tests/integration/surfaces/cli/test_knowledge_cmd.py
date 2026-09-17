"""Integration tests for `coffer knowledge ...` against the real stack.

We boot the full FastAPI app (via ``create_app``) so the knowledge kind is
wired with its production routes — real SQLite, real markdown files under a
temp HOME — then route ``_cli_client.client_or_exit`` at a Starlette
``TestClient`` over that app. Nothing auto-provisions any more: every
collection in here exists because a test created it (spec knowledge FR-008).

The group covers exactly FR-039's list and nothing beyond it. There is no
``grep`` and no ``search`` command any more: the corpus is plain Markdown under
``~/.coffer/knowledge/``, so a person's own ``grep`` is better than anything
this group could wrap — and the tests that drove those two commands are gone
with them rather than softened into asserting a different command.
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
    """Write one source and return the path the command printed.

    The command takes ``--in <collection>`` and never a lane: the ``sources/``
    segment belongs to the layer (spec knowledge FR-013), which is exactly what
    the returned path asserts.
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


# ----- collections ---------------------------------------------------------


def test_create_registers_a_collection_and_lists_it_with_both_lanes(knowledge_cli_daemon, tmp_path):
    _make_collection("shopee", "Internal systems")

    assert (tmp_path / "knowledge" / "shopee" / "sources").is_dir()
    assert (tmp_path / "knowledge" / "shopee" / "topics").is_dir()

    listed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "collections", "--json"])
    assert listed.exit_code == 0, listed.output
    collections = json.loads(_extract_json(listed.output))["collections"]
    assert [c["name"] for c in collections] == ["shopee"]
    assert collections[0]["description"] == "Internal systems"
    # The two counts are the honest picture: material held, versus material an
    # agent can reach (FR-001).
    assert (collections[0]["source_count"], collections[0]["topic_count"]) == (0, 0)


@pytest.mark.acceptance(
    spec="knowledge", scenario="the catalogue lists collections with their README description"
)
def test_catalogue_description_comes_from_the_readme(knowledge_cli_daemon, tmp_path):
    _make_collection("shopee", "First description")
    readme = tmp_path / "knowledge" / "shopee" / "README.md"
    readme.write_text("# shopee\n\nEdited by hand.\n", encoding="utf-8")

    listed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "collections", "--json"])
    collections = json.loads(_extract_json(listed.output))["collections"]
    # Read off disk on every listing, never out of a row (FR-011) — so the
    # string the creation call supplied is not what comes back.
    assert collections[0]["description"] == "Edited by hand."


def test_collections_renders_a_table_without_json(knowledge_cli_daemon):
    _make_collection("shopee", "Internal systems")
    listed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "collections"])
    assert listed.exit_code == 0, listed.output
    assert "shopee" in listed.output


# ----- writing and reading -------------------------------------------------


def test_write_lands_in_the_sources_lane_under_a_readable_name(knowledge_cli_daemon, tmp_path):
    _make_collection("shopee")

    path = _write("shopee", "Account Gateway", body="The orchestration layer.")

    assert path == "shopee/sources/account-gateway.md"
    assert (tmp_path / "knowledge" / path).is_file()


def test_write_can_nest_inside_the_lane(knowledge_cli_daemon, tmp_path):
    """FR-004: a folder is nesting inside ``sources/``, never beside it."""
    _make_collection("shopee")
    written = _runner.invoke(
        cli_app,
        [
            KIND_KNOWLEDGE,
            "write",
            "--title",
            "Gateway",
            "--description",
            "d",
            "--body",
            "b",
            "--in",
            "shopee",
            "--folder",
            "apis",
        ],
    )
    assert written.exit_code == 0, written.output
    assert written.output.strip().splitlines()[-1] == "shopee/sources/apis/gateway.md"


def test_read_returns_the_body_of_either_lane(knowledge_cli_daemon, tmp_path):
    _make_collection("shopee")
    path = _write("shopee", "Session", body="account.session owns login state")

    read = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "read", path])
    assert read.exit_code == 0, read.output
    assert "account.session owns login state" in read.output

    # A topic document reads exactly like a source; only editing it is refused.
    topics = tmp_path / "knowledge" / "shopee" / "topics"
    (topics / "derived.md").write_text(
        "---\ntitle: Derived\ndescription: d\nactor: agent\n"
        "created_at: '2026-09-17T00:00:00+00:00'\nupdated_at: '2026-09-17T00:00:00+00:00'\n"
        "---\n\nwhat curation concluded\n",
        encoding="utf-8",
    )
    read_topic = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "read", "shopee/topics/derived.md"])
    assert read_topic.exit_code == 0, read_topic.output
    assert "what curation concluded" in read_topic.output


def test_ls_lists_one_level_of_one_lane(knowledge_cli_daemon):
    _make_collection("shopee")
    path = _write("shopee", "Session")

    listed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "ls", "shopee/sources", "--json"])
    assert listed.exit_code == 0, listed.output
    data = json.loads(_extract_json(listed.output))
    assert [f["path"] for f in data["files"]] == [path]

    # The other lane is empty until a pass runs — the two are asked for
    # separately because the page draws two trees (FR-040).
    topics = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "ls", "shopee/topics", "--json"])
    assert json.loads(_extract_json(topics.output))["files"] == []


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
            "shopee/sources/t.md",
        ],
    )
    assert result.exit_code == 2


# ----- deleting ------------------------------------------------------------


def test_delete_removes_a_source_from_disk(knowledge_cli_daemon, tmp_path):
    _make_collection("shopee")
    path = _write("shopee", "Stale")
    on_disk = tmp_path / "knowledge" / path
    assert on_disk.is_file()

    removed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "delete", path])
    assert removed.exit_code == 0, removed.output
    assert not on_disk.exists()


def test_delete_refuses_a_topic_document(knowledge_cli_daemon, tmp_path):
    """FR-020: a topic is derived, and deleting one by hand would offer a
    delete the next pass silently undoes."""
    _make_collection("shopee")
    topic = tmp_path / "knowledge" / "shopee" / "topics" / "derived.md"
    topic.write_text(
        "---\ntitle: Derived\ndescription: d\nactor: agent\n"
        "created_at: '2026-09-17T00:00:00+00:00'\nupdated_at: '2026-09-17T00:00:00+00:00'\n"
        "---\n\nb\n",
        encoding="utf-8",
    )

    removed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "delete", "shopee/topics/derived.md"])
    assert removed.exit_code != 0
    assert topic.is_file()


# ----- upload and curate ---------------------------------------------------


def test_cli_upload_lands_the_conversion_and_its_original(knowledge_cli_daemon, tmp_path):
    _make_collection("shopee")
    # A CSV, so the conversion genuinely differs from the bytes uploaded and an
    # original is worth keeping. A `.txt` or `.md` converts by passthrough and
    # lands once — see the test below.
    source = tmp_path / "team.csv"
    source.write_bytes(b"name,owner\nsession,account\n")

    result = _runner.invoke(
        cli_app,
        [KIND_KNOWLEDGE, "upload", str(source), "--collection", "shopee"],
    )
    assert result.exit_code == 0, result.output
    # The Markdown is named for the document's own title, not for the file it
    # arrived as (FR-002).
    path = result.output.strip().splitlines()[-1]
    assert path == "shopee/sources/team.md"
    assert (tmp_path / "knowledge" / path).is_file()
    # The original keeps its own name and extension, as a visible file in the
    # same lane (FR-016).
    assert (tmp_path / "knowledge" / "shopee" / "sources" / "team.csv").read_bytes() == (
        source.read_bytes()
    )


def test_cli_upload_of_plain_text_lands_once(knowledge_cli_daemon, tmp_path):
    """Passthrough means the file that landed IS the original (FR-016).

    Keeping a second copy would put one document in the lane twice and hand the
    curation pass the same facts as two independent sources.
    """
    _make_collection("shopee")
    source = tmp_path / "notes.txt"
    source.write_text("# Runbook\n\nAccount gateway owns the session cache.\n", encoding="utf-8")

    result = _runner.invoke(
        cli_app,
        [KIND_KNOWLEDGE, "upload", str(source), "--collection", "shopee"],
    )
    assert result.exit_code == 0, result.output

    lane = tmp_path / "knowledge" / "shopee" / "sources"
    assert sorted(p.name for p in lane.iterdir()) == ["runbook.md"]


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
    """FR-029: with no internal connection configured a pass is a clean no-op,
    and the status IS the answer — not an error the CLI has to invent."""
    _make_collection("shopee")
    _write("shopee", "Session")

    result = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "curate", "shopee"])
    assert result.exit_code == 0, result.output
    outcome = json.loads(_extract_json(result.output))
    assert outcome["status"] == "no_model"
    assert outcome["collection"] == "shopee"


def test_cli_curate_on_an_unknown_collection_is_an_error(knowledge_cli_daemon):
    result = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "curate", "typo"])
    assert result.exit_code != 0
