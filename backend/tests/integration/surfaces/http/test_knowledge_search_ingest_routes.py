"""Integration tests for the knowledge layer's search and ingest routes:
``POST /search`` and ``POST /upload`` (spec knowledge FR-024..FR-027,
FR-033..FR-037, FR-060).

We boot the full FastAPI app (via ``create_app``) so these routes are wired
exactly as production wires them — real SQLite, real markdown files under a
temp HOME, the real converter registry — then drive them with a Starlette
``TestClient`` (an ``httpx.Client`` subclass). Search needs nothing configured:
it is ripgrep over the files, with no model, key or connection behind it.

``client``, ``_create_collection`` and ``_write_file`` live in ``conftest.py``.
"""

from __future__ import annotations

import pytest

from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.knowledge.builtin_tools import register_knowledge_builtin_tools
from coffer.application.knowledge.search import SearchService
from coffer.surfaces.http.knowledge.dependencies import get_knowledge_service

from .conftest import _create_collection, _write_file

# ----- search --------------------------------------------------------------


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="search returns the files a phrase appears in, with the lines that matched",
)
def test_search_returns_the_files_a_phrase_appears_in(client) -> None:
    _create_collection(client, "shopee")
    path = _write_file(
        client,
        directory="shopee",
        title="Session Ownership",
        description="Which service owns a login session",
        body="account.session owns login state",
    )

    resp = client.post(
        "/api/v1/knowledge/search", json={"query": "account.session owns login state"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert any(r["path"] == path for r in data["results"])
    hit = next(r for r in data["results"] if r["path"] == path)
    assert hit["title"] == "Session Ownership"
    assert hit["description"] == "Which service owns a login session"
    assert hit["lines"]


def test_search_over_an_unknown_collection_is_not_found(client) -> None:
    resp = client.post("/api/v1/knowledge/search", json={"query": "x", "collection": "typo"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "KNOWLEDGE_COLLECTION_NOT_FOUND"


@pytest.mark.acceptance(
    spec="knowledge", scenario="search spans only the collections the caller may see"
)
async def test_builtin_search_tool_spans_only_the_agents_collections(client) -> None:
    """REST ``search`` is the owner's unscoped surface (FR-060); the same
    ``SearchService`` this route wires is also what the built-in ``search``
    MCP tool calls with an ``agent``, and that call IS scoped (FR-012). Restrict
    a second collection to an unrelated agent (via the framework's scope
    route) and confirm this caller's results never cross into it."""
    _create_collection(client, "shopee")
    _write_file(
        client,
        directory="shopee",
        title="Open note",
        description="d",
        body="account.session owns login state",
    )
    _create_collection(client, "secret")
    _write_file(
        client,
        directory="secret",
        title="Hidden note",
        description="d",
        body="account.session owns login state too",
    )
    scoped = client.put(
        "/api/v1/resources/knowledge/secret/scope",
        json={"scope": {"agents": ["only-agent"]}},
    )
    assert scoped.status_code == 200, scoped.text

    knowledge_service = get_knowledge_service()
    search_service = SearchService(knowledge=knowledge_service)
    registry = BuiltinToolRegistry()
    register_knowledge_builtin_tools(
        registry, knowledge_service=knowledge_service, search_service=search_service
    )
    tool = registry.get("coffer__search")
    assert tool is not None

    outcome = await tool.handler({"query": "login state", "agent": "some-other-agent"})
    assert any(r["path"].startswith("shopee/") for r in outcome["results"])
    assert all(not r["path"].startswith("secret/") for r in outcome["results"])


def test_search_returns_nothing_rather_than_erroring_for_an_unmatched_query(client) -> None:
    _create_collection(client, "shopee")
    _write_file(client, directory="shopee", title="t", description="d", body="account.session")

    resp = client.post("/api/v1/knowledge/search", json={"query": "nothingmatchesthis"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["results"] == []


# ----- upload ----------------------------------------------------------------


@pytest.mark.acceptance(
    spec="knowledge", scenario="an uploaded document lands as markdown with frontmatter"
)
def test_upload_lands_as_markdown_with_frontmatter(client) -> None:
    _create_collection(client, "shopee")

    resp = client.post(
        "/api/v1/knowledge/upload",
        data={"collection": "shopee"},
        files={"file": ("Runbook.txt", b"Runbook\n\nAccount gateway owns the session cache.\n")},
    )
    assert resp.status_code == 201, resp.text
    doc = resp.json()
    assert doc["path"].startswith("shopee/") and doc["path"].endswith(".md")
    assert doc["converter"] == "passthrough"
    assert doc["title"]
    assert doc["description"]

    read = client.get("/api/v1/knowledge/file", params={"path": doc["path"]})
    assert read.status_code == 200, read.text
    file_out = read.json()
    assert file_out["actor"] == "user"
    assert file_out["title"] == doc["title"]
    assert file_out["description"] == doc["description"]
    assert "Account gateway owns the session cache." in file_out["body"]


@pytest.mark.acceptance(
    spec="knowledge", scenario="an uploaded original is kept under .raw/ and stays out of retrieval"
)
def test_upload_keeps_the_original_under_raw_and_out_of_retrieval(client, tmp_path) -> None:
    _create_collection(client, "shopee")

    resp = client.post(
        "/api/v1/knowledge/upload",
        data={"collection": "shopee"},
        files={"file": ("Runbook.txt", b"Runbook\n\nOnly the original says banana-marker.\n")},
    )
    assert resp.status_code == 201, resp.text
    doc = resp.json()

    raw_path = tmp_path / "knowledge" / "shopee" / ".raw" / "runbook.txt"
    assert raw_path.is_file()
    assert doc["raw_path"] == str(raw_path)
    assert b"banana-marker" in raw_path.read_bytes()

    tree = client.get("/api/v1/knowledge/tree", params={"path": "shopee"})
    assert tree.status_code == 200
    assert all(".raw" not in f["path"] for f in tree.json()["files"])

    grep = client.get("/api/v1/knowledge/grep", params={"pattern": "banana-marker"})
    assert grep.status_code == 200
    assert all(".raw" not in m["path"] for m in grep.json()["matches"])


@pytest.mark.acceptance(
    spec="knowledge", scenario="an upload of an unsupported type is refused with its reason"
)
def test_upload_of_unsupported_type_is_refused_with_its_reason(client) -> None:
    _create_collection(client, "shopee")

    resp = client.post(
        "/api/v1/knowledge/upload",
        data={"collection": "shopee"},
        files={"file": ("payload.exe", b"\x00\x01\x02")},
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["error"]["code"] == "INGEST_REJECTED"
    assert body["error"]["details"]["reason"] == "unsupported_type"
    assert body["error"]["details"]["doc_type"] == "exe"


def test_upload_into_an_unknown_collection_is_not_found(client) -> None:
    resp = client.post(
        "/api/v1/knowledge/upload",
        data={"collection": "typo"},
        files={"file": ("notes.txt", b"hello")},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "KNOWLEDGE_COLLECTION_NOT_FOUND"


def test_oversize_upload_is_refused_and_names_the_limit(client, monkeypatch) -> None:
    import coffer.application.knowledge.ingest as ingest_module

    monkeypatch.setattr(ingest_module, "MAX_UPLOAD_BYTES", 8)
    _create_collection(client, "shopee")

    resp = client.post(
        "/api/v1/knowledge/upload",
        data={"collection": "shopee"},
        files={"file": ("notes.txt", b"this payload is well over eight bytes")},
    )
    assert resp.status_code == 413, resp.text
    body = resp.json()
    assert body["error"]["code"] == "KNOWLEDGE_UPLOAD_TOO_LARGE"
    assert "8" in body["error"]["message"]
