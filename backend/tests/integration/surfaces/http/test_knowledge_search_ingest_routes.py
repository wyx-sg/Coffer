"""Integration tests for the knowledge layer's search and ingest routes:
``POST /search`` and ``POST /upload`` (spec knowledge FR-016..FR-018,
FR-022..FR-026, FR-034).

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
from coffer.domain.knowledge.converter import Conversion
from coffer.infrastructure.knowledge.converters.registry import ConverterRegistry
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
    """REST ``search`` is the owner's unscoped surface (FR-034); the same
    ``SearchService`` this route wires is also what the built-in ``search``
    MCP tool calls with an ``agent``, and that call IS scoped (FR-009). Restrict
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
    """FR-024: the original is kept, and retrieval never reaches it.

    The arrangement is what makes this provable, and it is the reason the
    fixture is HTML rather than the `.txt` this test used to send. Passthrough
    copies a `.txt` verbatim, so every marker in the original is also in the
    converted Markdown and `.raw/` exclusion cannot be distinguished from
    conversion: the old `all(".raw" not in m["path"] ...)` shape passed on a
    single match that came from the Markdown, and would have passed just as
    happily on zero matches if grep had broken outright.

    An HTML comment is dropped by the converter, so `banana-marker` lives in
    `.raw/runbook.html` and nowhere else, while `session cache` is in BOTH the
    original and the conversion. That gives two assertions with teeth:

    * the raw-only marker must return **exactly nothing** — one hit means grep
      descended into `.raw/`;
    * the shared phrase must return hits, and every hit's path must be the
      converted file — which is the positive control that proves the empty
      result above is exclusion rather than a grep that stopped working.
    """
    _create_collection(client, "shopee")

    resp = client.post(
        "/api/v1/knowledge/upload",
        data={"collection": "shopee"},
        files={
            "file": (
                "Runbook.html",
                b"<html><head><title>Runbook</title></head><body>"
                b"<!-- banana-marker -->"
                b"<p>Account gateway owns the session cache.</p>"
                b"</body></html>",
            )
        },
    )
    assert resp.status_code == 201, resp.text
    doc = resp.json()

    raw_path = tmp_path / "knowledge" / "shopee" / ".raw" / "runbook.html"
    assert raw_path.is_file()
    assert doc["raw_path"] == str(raw_path)
    assert b"banana-marker" in raw_path.read_bytes()
    # The premise the two grep assertions rest on: the marker survived into the
    # original and did NOT survive into the conversion.
    converted = client.get("/api/v1/knowledge/file", params={"path": doc["path"]})
    assert converted.status_code == 200, converted.text
    assert "banana-marker" not in converted.json()["body"]

    tree = client.get("/api/v1/knowledge/tree", params={"path": "shopee"})
    assert tree.status_code == 200
    # Exact, not "nothing under .raw/": the converted file is the only thing
    # the tree may carry, and `.raw` is not a directory it may offer either.
    assert [f["path"] for f in tree.json()["files"]] == [doc["path"]]
    assert tree.json()["directories"] == []

    grep = client.get("/api/v1/knowledge/grep", params={"pattern": "banana-marker"})
    assert grep.status_code == 200
    assert grep.json()["matches"] == [], (
        f"a marker that exists only under .raw/ must match nothing at all: {grep.json()['matches']}"
    )

    shared = client.get("/api/v1/knowledge/grep", params={"pattern": "session cache"})
    assert shared.status_code == 200
    hits = shared.json()["matches"]
    assert hits, "grep found nothing for a phrase the converted file contains"
    assert {m["path"] for m in hits} == {doc["path"]}, (
        "a phrase present in both the original and the conversion must be "
        f"reported only from the conversion: {sorted({m['path'] for m in hits})}"
    )


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


@pytest.mark.acceptance(spec="knowledge", scenario="a document is never stored half-converted")
def test_upload_of_a_pdf_with_no_text_layer_is_refused_as_scanned(client, monkeypatch) -> None:
    """FR-026, end to end, including the reason the UI keys its message off.

    A real image-only PDF is not worth carrying as a fixture: the rule is that
    ANY conversion producing no text is refused, so the converter is made to
    return ``""`` — which is exactly what MarkItDown does for a scanned PDF,
    without raising.
    """
    _create_collection(client, "shopee")

    async def _empty(self, data, filename):  # type: ignore[no-untyped-def]
        return Conversion(markdown="", title="Scan", converter="markitdown")

    monkeypatch.setattr(ConverterRegistry, "convert", _empty)

    resp = client.post(
        "/api/v1/knowledge/upload",
        data={"collection": "shopee"},
        files={"file": ("scan.pdf", b"%PDF-1.7 image only")},
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["error"]["code"] == "INGEST_REJECTED"
    # The key `frontend/src/i18n/locales/{en,zh}.json` already define as
    # `INGEST_REJECTED_scanned_pdf` — it was a message with no producer.
    assert body["error"]["details"]["reason"] == "scanned_pdf"
    assert body["error"]["details"]["doc_type"] == "pdf"

    tree = client.get("/api/v1/knowledge/tree", params={"path": "shopee"})
    assert tree.json()["files"] == []


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
