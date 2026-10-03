"""Integration tests for `coffer knowledge ...` against the real stack.

We boot the full FastAPI app (via ``create_app``) so the knowledge kind is
wired with its production routes — real SQLite, real markdown files under a
temp HOME — then route ``_cli_client.client_or_exit`` at a Starlette
``TestClient`` over that app. Nothing auto-provisions any more: every
collection in here exists because a test created it (spec knowledge "Create
collections only deliberately").

The group covers exactly the list in "Cover knowledge management on REST and
the CLI" and nothing beyond it: the lifecycle verbs (no ``enable``/``disable``,
since every collection is served to every agent), ``write``, ``upload``,
``curate`` and the history commands. Documents are plain Markdown under
``~/.coffer/knowledge/``, so the group neither lists, prints nor deletes one —
``coffer path knowledge`` names the directory (test_path_cmd.py) and a person's
own tools do the rest.
"""

from __future__ import annotations

import json
import pathlib
from datetime import UTC
from datetime import datetime as dt

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.application.knowledge.service import KIND_KNOWLEDGE
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.infrastructure.knowledge.paths import knowledge_root as _knowledge_root
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
    created = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "add", name, "--description", description])
    assert created.exit_code == 0, created.output


def _write(collection: str, title: str, body: str = "b", description: str = "d") -> str:
    """Submit one piece of material and return the line the command printed.

    The command takes ``--collection <collection>`` and never a path: where knowledge
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
            "--collection",
            collection,
        ],
    )
    assert written.exit_code == 0, written.output
    return written.output.strip().splitlines()[-1]


def _document(tmp_path, relpath: str, body: str) -> None:  # type: ignore[no-untyped-def]
    """A document written straight into the tree, as a person's editor would."""
    path = _knowledge_root() / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\ntitle: Derived\ndescription: d\nactor: agent\n"
        "created_at: '2026-09-17T00:00:00+00:00'\nupdated_at: '2026-09-17T00:00:00+00:00'\n"
        f"---\n\n{body}\n",
        encoding="utf-8",
    )


# ----- collections ---------------------------------------------------------


def test_add_registers_a_collection_and_lists_it(knowledge_cli_daemon, tmp_path):
    _make_collection("shopee", "Internal systems")

    collection = _knowledge_root() / "shopee"
    assert collection.is_dir()
    assert not (collection / "sources").exists() and not (collection / "topics").exists()

    listed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "list", "--json"])
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
    readme = _knowledge_root() / "shopee" / "README.md"
    readme.write_text("# shopee\n\nEdited by hand.\n", encoding="utf-8")

    listed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "list", "--json"])
    collections = json.loads(_extract_json(listed.output))["collections"]
    # Read off disk on every listing, never out of a row ("Read a collection's
    # description from its README") — so the
    # string the creation call supplied is not what comes back.
    assert collections[0]["description"] == "Edited by hand."


def test_list_renders_a_table_without_json(knowledge_cli_daemon):
    _make_collection("shopee", "Internal systems")
    listed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "list"])
    assert listed.exit_code == 0, listed.output
    assert "shopee" in listed.output


# ----- writing and reading -------------------------------------------------


def test_write_becomes_a_document_under_a_readable_name(knowledge_cli_daemon, tmp_path):
    _make_collection("shopee")

    path = _write("shopee", "Account Gateway", body="The orchestration layer.")

    assert path == "shopee/account-gateway.md"
    assert (_knowledge_root() / path).is_file()


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
    assert [p.name for p in (_knowledge_root() / "shopee" / ".inbox").iterdir()] == ["gateway.md"]


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
                "--collection",
                "shopee",
                flag,
                value,
            ],
        )
        assert result.exit_code == 2, result.output


@pytest.mark.acceptance(
    spec="knowledge", scenario="an unknown collection is an error, never auto-created"
)
def test_unknown_collection_is_an_error(knowledge_cli_daemon, tmp_path):
    shown = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "show", "typo", "--json"])
    assert shown.exit_code != 0
    located = _runner.invoke(cli_app, ["path", "knowledge", "typo"])
    assert located.exit_code != 0
    assert not (_knowledge_root() / "typo").exists()


# ----- the lifecycle verbs ---------------------------------------------------


def test_show_edit_and_rm_a_collection(knowledge_cli_daemon, tmp_path):
    """The verbs every kind shares, on a collection: by name, and by uid."""
    _make_collection("shopee")

    shown = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "show", "shopee", "--json"])
    assert shown.exit_code == 0, shown.output
    uid = json.loads(_extract_json(shown.output))["uid"]

    # No title: a collection is shown by its folder name.
    titled = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "edit", "shopee", "--title", "Shopee"])
    assert titled.exit_code == 2, titled.output
    by_uid = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "show", uid, "--json"])
    assert json.loads(_extract_json(by_uid.output))["name"] == "shopee"

    # No switch: every collection is served to every agent (spec knowledge
    # "Serve every collection to every agent").
    assert _runner.invoke(cli_app, [KIND_KNOWLEDGE, "disable", "shopee"]).exit_code == 2
    assert _daemon().get(f"/resources/{uid}").json()["enabled"] is True

    removed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "rm", "shopee", "--yes"])
    assert removed.exit_code == 0, removed.output
    listed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "list", "--json"])
    assert json.loads(_extract_json(listed.output))["collections"] == []


def test_edit_rewrites_the_description_in_the_readme(knowledge_cli_daemon, tmp_path):
    """A collection's description is its README's opening paragraph (spec
    knowledge "Read a collection's description from its README"): `edit
    --description` rewrites that paragraph, and nothing is stored in the row."""
    _make_collection("shopee", "Old words.")
    edited = _runner.invoke(
        cli_app, [KIND_KNOWLEDGE, "edit", "shopee", "--description", "Shopee's services."]
    )
    assert edited.exit_code == 0, edited.output
    readme = (_knowledge_root() / "shopee" / "README.md").read_text(encoding="utf-8")
    assert readme == "# shopee\n\nShopee's services.\n"
    listed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "list", "--json"])
    rows = json.loads(_extract_json(listed.output))["collections"]
    assert rows[0]["description"] == "Shopee's services."
    assert _daemon().get(f"/resources/{rows[0]['uid']}").json()["description"] in (None, "")
    nothing = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "edit", "shopee"])
    assert nothing.exit_code == 2, nothing.output


def test_add_takes_no_title(knowledge_cli_daemon):
    """A collection has no title — it is shown by its folder name."""
    added = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "add", "shopee", "--title", "Shopee"])
    assert added.exit_code == 2, added.output


def test_restore_deleted_brings_a_removed_collection_back(knowledge_cli_daemon, tmp_path):
    """spec knowledge "Restore a deleted collection or document from Recent changes":
    `restore --deleted` names the delete's version from `changes`."""
    _make_collection("shopee", "Shopee services.")
    doc = _write("shopee", "Cache", body="kept")
    assert _runner.invoke(cli_app, [KIND_KNOWLEDGE, "rm", "shopee", "--yes"]).exit_code == 0
    feed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "changes", "--json"])
    removal = next(
        c for c in json.loads(_extract_json(feed.output))["changes"] if c["operation"] == "remove"
    )

    restored = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "restore", "--deleted", removal["version"]])
    assert restored.exit_code == 0, restored.output
    assert doc in restored.output
    assert (_knowledge_root() / doc).is_file()
    listed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "list", "--json"])
    rows = json.loads(_extract_json(listed.output))["collections"]
    assert [(r["name"], r["description"]) for r in rows] == [("shopee", "Shopee services.")]
    both = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "restore", doc, "abc123", "--deleted", "x"])
    assert both.exit_code == 2, both.output


def test_the_route_refuses_to_delete_the_readme(knowledge_cli_daemon, tmp_path):
    """The README describes the collection rather than being a document in it."""
    _make_collection("shopee")

    resp = _daemon().delete("/knowledge/file", params={"path": "shopee/README.md"})
    assert resp.status_code >= 400, resp.text
    assert (_knowledge_root() / "shopee" / "README.md").is_file()


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
    assert (_knowledge_root() / path).is_file()
    # The original is not kept: the collection holds knowledge, not the
    # documents it arrived in ("Convert uploads into material without keeping
    # them").
    collection = _knowledge_root() / "shopee"
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

    result = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "curate", "shopee", "--json"])
    assert result.exit_code == 0, result.output
    run = json.loads(_extract_json(result.output))
    assert run["status"] == "no_model"
    assert run["collection"] == "shopee"
    # The material was already promoted when it arrived, so nothing was left.
    assert [p["promoted"] for p in run["passes"]] == [[]]

    human = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "curate", "shopee"])
    assert human.exit_code == 0, human.output
    assert "Coffer's model is not set" in human.output


def test_cli_curate_takes_one_document(knowledge_cli_daemon):
    """``--document`` carries one edited document through; with no model the
    answer is still the honest ``no_model``, not an error."""
    _make_collection("shopee")
    path = _write("shopee", "Session")

    result = _runner.invoke(
        cli_app, [KIND_KNOWLEDGE, "curate", "shopee", "--document", path, "--json"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(_extract_json(result.output))["status"] == "no_model"


@pytest.mark.acceptance(spec="knowledge", scenario="curate now reports progress")
def test_cli_curate_prints_n_of_m_for_each_pass(knowledge_cli_daemon, monkeypatch):
    """Curate now drains, and the command prints each pass as 1 of 3, 2 of 3,
    3 of 3 — the same progress the in-flight list reports."""
    from coffer.infrastructure.knowledge import inbox
    from coffer.surfaces.http.knowledge import curation_state

    _make_collection("shopee")
    _hold_material(monkeypatch)
    for title in ("One", "Two", "Three"):
        _write("shopee", title)

    async def settle(service, uid, *, item, actor):  # type: ignore[no-untyped-def]
        inbox.discard_material("shopee", item.material)
        return {"status": "ok", "collection": "shopee", "item": f"shopee/.inbox/{item.material}"}

    monkeypatch.setattr(curation_state, "_curation_runner", settle)
    result = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "curate", "shopee"])

    assert result.exit_code == 0, result.output
    lines = [line for line in result.output.splitlines() if " of 3: ok " in line]
    assert [line.split(":")[0] for line in lines] == ["1 of 3", "2 of 3", "3 of 3"]
    items = sorted(line.split()[4].rsplit("/", 1)[-1] for line in lines)
    assert items == ["one.md", "three.md", "two.md"]
    assert "shopee: curated 3 of 3" in result.output


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

    collection = _knowledge_root() / "shopee"
    assert sorted(p.name for p in (collection / ".inbox").iterdir()) == [
        "from-the-cli.md",
        "from-the-route.md",
    ]
    visible = [
        p for p in collection.rglob("*.md") if ".inbox" not in p.parts and p.name != "README.md"
    ]
    assert visible == []


@pytest.mark.acceptance(spec="knowledge", scenario="delete a document an agent wrote")
def test_a_person_deletes_agent_written_documents_by_route_and_on_disk(
    knowledge_cli_daemon, tmp_path
):
    _make_collection("shopee")
    _document(tmp_path, "shopee/by-route.md", "b")
    _document(tmp_path, "shopee/by-hand.md", "b")
    for name in ("by-route.md", "by-hand.md"):
        assert "actor: agent" in (_knowledge_root() / "shopee" / name).read_text()

    resp = _daemon().delete("/knowledge/file", params={"path": "shopee/by-route.md"})
    assert resp.status_code == 204, resp.text
    located = _runner.invoke(cli_app, ["path", "knowledge", "shopee"])
    assert located.exit_code == 0, located.output
    directory = located.output.strip().splitlines()[-1]
    (pathlib.Path(directory) / "by-hand.md").unlink()

    assert not (_knowledge_root() / "shopee" / "by-route.md").exists()
    assert not (_knowledge_root() / "shopee" / "by-hand.md").exists()
    tree = _daemon().get("/knowledge/tree", params={"path": "shopee"}).json()
    assert tree["files"] == []
    listed = _runner.invoke(cli_app, [KIND_KNOWLEDGE, "list", "--json"])
    assert json.loads(_extract_json(listed.output))["collections"][0]["document_count"] == 0
    audit = _daemon().get("/audit", params={"event_type": "knowledge_deleted"})
    assert audit.status_code == 200, audit.text
    deleted = sorted(e["details"]["path"] for e in audit.json()["entries"])
    assert deleted == ["shopee/by-route.md"]


_KNOWLEDGE_OPERATIONS = {
    ("POST", "/api/v1/knowledge/collections"),
    ("GET", "/api/v1/knowledge/tree"),
    ("GET", "/api/v1/knowledge/file"),
    ("PUT", "/api/v1/knowledge/file"),
    ("POST", "/api/v1/knowledge/material"),
    ("POST", "/api/v1/knowledge/upload"),
    ("DELETE", "/api/v1/knowledge/file"),
    ("POST", "/api/v1/knowledge/collections/{uid}/curate"),
    ("GET", "/api/v1/knowledge/history"),
    ("GET", "/api/v1/knowledge/history/diff"),
    ("POST", "/api/v1/knowledge/history/restore"),
    ("GET", "/api/v1/knowledge/changes"),
    ("GET", "/api/v1/knowledge/changes/{version}"),
    ("POST", "/api/v1/knowledge/changes/{version}/undo"),
    ("POST", "/api/v1/knowledge/changes/{version}/restore"),
    ("GET", "/api/v1/knowledge/history/version"),
    ("PUT", "/api/v1/knowledge/collections/{uid}/description"),
}
_KNOWLEDGE_COMMANDS = [
    "list",
    "show",
    "add",
    "edit",
    "rm",
    "write",
    "upload",
    "curate",
    "history",
    "restore",
    "changes",
    "undo",
]
_FORBIDDEN_ROUTE_WORDS = ("index", "reindex", "source", "embedding", "scope", "reach")


@pytest.mark.acceptance(
    spec="knowledge", scenario="expose every knowledge operation on both surfaces"
)
def test_rest_and_cli_cover_every_knowledge_operation(knowledge_cli_daemon):
    import typer.main

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

    group = typer.main.get_command(cli_app).commands[KIND_KNOWLEDGE]  # type: ignore[attr-defined]
    assert list(group.commands) == _KNOWLEDGE_COMMANDS

    for method, path in routes:
        tail = path.removeprefix("/api/v1/knowledge").lower()
        assert not any(word in tail for word in _FORBIDDEN_ROUTE_WORDS), path
        # No route creates a document at a path: new knowledge is material
        # submitted like every other entrance.
        assert not (method == "POST" and tail in {"/file", "/document", "/documents"}), path
