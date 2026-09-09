"""HTTP tests for the document half of ``/api/v1/knowledge/*``.

Pins the *route* layer: the standard {error:{code,message,details}} envelope,
status codes, the upload size guard, and one full real-substrate document flow
(ingest → get → edit → reconvert → reindex → grep → delete). Shape-only cases
use dependency-override fakes so they stay fast; the flow test runs the real
SQLite/FTS5 + file substrate.

The scope surface (list / create / metrics / 404) is exercised once in
``test_knowledge_entry_routes.py`` — after the merge there is one scope route
tree, so it is not re-asserted here.
"""

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_TOKEN = "knowledge-doc-routes-token"
_HEADERS = {"X-Coffer-Token": _TOKEN}


def _app(tmp_path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    return create_app()


def _assert_envelope(body: dict, code: str) -> None:
    assert "error" in body, body
    assert body["error"]["code"] == code, body
    assert isinstance(body["error"]["message"], str)
    assert isinstance(body["error"]["details"], dict)


def _create_scope(c, name: str, config: dict | None = None) -> None:
    r = c.post(
        "/api/v1/knowledge",
        json={"name": name, "config": config if config is not None else {}},
        headers=_HEADERS,
    )
    assert r.status_code == 201, r.text


# --------------------------------------------------------------------------- #
# ingest guards
# --------------------------------------------------------------------------- #


def test_oversized_upload_rejected_with_413_envelope(tmp_path, monkeypatch):
    """The per-scope max_document_bytes limit yields 413 with reason=too_large."""
    app = _app(tmp_path, monkeypatch, 59430)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        _create_scope(c, "tiny", {"max_document_bytes": 1024})
        r = c.post(
            "/api/v1/knowledge/tiny/documents",
            files={"file": ("big.md", b"x" * 4096, "text/plain")},
            headers=_HEADERS,
        )
        assert r.status_code == 413, r.text
        body = r.json()
        _assert_envelope(body, "INGEST_REJECTED")
        assert body["error"]["details"]["reason"] == "too_large"


def test_upload_route_guard_rejects_before_buffering(tmp_path, monkeypatch):
    """The absolute-ceiling guard in the route rejects an oversized upload
    via file.size. The scope's own limit (25 MB default) is far larger than the
    payload, so a 413 here can only come from the route-level guard."""
    from coffer.surfaces.http.knowledge import document_routes

    monkeypatch.setattr(document_routes, "_ABSOLUTE_MAX_DOC_BYTES", 64)
    app = _app(tmp_path, monkeypatch, 59440)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        _create_scope(c, "kb")
        r = c.post(
            "/api/v1/knowledge/kb/documents",
            files={"file": ("big.md", b"x" * 256, "text/plain")},
            headers=_HEADERS,
        )
        assert r.status_code == 413, r.text
        _assert_envelope(r.json(), "INGEST_REJECTED")


def test_get_missing_document_returns_envelope(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59450)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        _create_scope(c, "kb")
        r = c.get("/api/v1/knowledge/kb/documents/nope", headers=_HEADERS)
        assert r.status_code == 404
        _assert_envelope(r.json(), "DOCUMENT_NOT_FOUND")


def test_delete_document_returns_bodyless_204(tmp_path, monkeypatch):
    """A successful document delete returns a bodyless 204. The knowledge service
    is faked so the route is exercised without a real ingested document."""
    from coffer.surfaces.http.dependencies import get_knowledge_service

    class _FakeKnowledgeService:
        def __init__(self) -> None:
            self.deleted: list[tuple[str, str]] = []

        async def delete_document(self, *, scope_name: str, document_id: str, actor: str) -> None:
            self.deleted.append((scope_name, document_id))

    fake = _FakeKnowledgeService()
    app = _app(tmp_path, monkeypatch, 59460)
    app.dependency_overrides[get_knowledge_service] = lambda: fake
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.delete("/api/v1/knowledge/kb/documents/d1", headers=_HEADERS)
        assert r.status_code == 204, r.text
        assert r.content == b""
    assert fake.deleted == [("kb", "d1")]


# --------------------------------------------------------------------------- #
# TEST22-016 — search route coverage
# --------------------------------------------------------------------------- #


class _SearchFakeKnowledgeService:
    """Fake knowledge service returning canned passages so the route layer is
    exercised without booting the converter/embedder or writing docs.

    Matches the merged service contract: ``search`` takes ``scope_name`` +
    ``mode`` and returns a ``SearchResult``."""

    def __init__(self) -> None:
        self.searches: list[tuple[str, str, int]] = []

    async def search(self, *, scope_name: str, query: str, top_k: int, mode=None):
        from coffer.domain.knowledge.retrieval import Passage, SearchResult

        self.searches.append((scope_name, query, top_k))
        passages = [
            Passage(
                document_id="doc-1",
                title="prefs.md",
                text="the user prefers tabs",
                score=0.91,
                position=0,
            ),
            Passage(
                document_id="doc-2",
                title="prefs2.md",
                text="more tabs context",
                score=0.42,
                position=1,
            ),
        ][:top_k]
        return SearchResult(mode="keyword", passages=tuple(passages), fallback=None)


def test_search_route_returns_ranked_hits(tmp_path, monkeypatch):
    """TEST22-016: POST /search → 200 with the SearchResponse envelope."""
    from coffer.surfaces.http.dependencies import get_knowledge_service

    fake = _SearchFakeKnowledgeService()
    app = _app(tmp_path, monkeypatch, 59470)
    app.dependency_overrides[get_knowledge_service] = lambda: fake
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        # The scope doesn't need to exist on the resource_service when the
        # knowledge service is fully faked — the route forwards directly to it.
        r = c.post(
            "/api/v1/knowledge/kb/search",
            json={"query": "tabs", "top_k": 2},
            headers=_HEADERS,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # mode / fallback are no longer surfaced (one query → one answer).
        assert "mode" not in body
        assert "fallback" not in body
        assert isinstance(body["passages"], list)
        assert len(body["passages"]) == 2
        hit = body["passages"][0]
        assert set(hit.keys()) >= {"text", "document_id", "title", "score", "position"}
        assert hit["title"] == "prefs.md"
        assert hit["score"] == pytest.approx(0.91)
    assert fake.searches == [("kb", "tabs", 2)]


# --------------------------------------------------------------------------- #
# TEST22-012 — top_k validation boundaries
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("top_k", [0, 21, -1, 100])
def test_search_top_k_out_of_range_422(tmp_path, monkeypatch, top_k):
    """TEST22-012: ``top_k`` outside [1, 20] is rejected by the route's
    Pydantic schema as 422, never reaches the knowledge service."""
    from coffer.surfaces.http.dependencies import get_knowledge_service

    fake = _SearchFakeKnowledgeService()
    app = _app(tmp_path, monkeypatch, 59490 + abs(top_k) % 5)
    app.dependency_overrides[get_knowledge_service] = lambda: fake
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post(
            "/api/v1/knowledge/kb/search",
            json={"query": "tabs", "top_k": top_k},
            headers=_HEADERS,
        )
        assert r.status_code == 422, r.text
    assert fake.searches == []  # service never called


# --------------------------------------------------------------------------- #
# TEST22-020 — engine unavailable 503
# --------------------------------------------------------------------------- #


def test_search_engine_unavailable_returns_503(tmp_path, monkeypatch):
    """TEST22-020: a scope that raises ``EngineUnavailable`` surfaces as
    HTTP 503 with ``error.code == "ENGINE_UNAVAILABLE"``."""
    from coffer.domain.errors import EngineUnavailable
    from coffer.surfaces.http.dependencies import get_knowledge_service

    class _FailingKnowledgeService:
        async def search(self, *, scope_name: str, query: str, top_k: int, mode=None):
            raise EngineUnavailable(
                "embedding",
                "test: engine not installed",
            )

    app = _app(tmp_path, monkeypatch, 59500)
    app.dependency_overrides[get_knowledge_service] = lambda: _FailingKnowledgeService()
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post(
            "/api/v1/knowledge/kb/search",
            json={"query": "anything", "top_k": 3},
            headers=_HEADERS,
        )
        assert r.status_code == 503, r.text
        _assert_envelope(r.json(), "ENGINE_UNAVAILABLE")


def test_metrics_engine_unavailable_returns_503(tmp_path, monkeypatch):
    """Companion: metrics also surfaces EngineUnavailable through the app-
    wide error handler (the surface treats it uniformly)."""
    from coffer.domain.errors import EngineUnavailable
    from coffer.surfaces.http.dependencies import get_knowledge_service

    class _FailingKnowledgeService:
        async def metrics(self, *, scope_name: str) -> dict[str, object]:
            raise EngineUnavailable("embedding", "test: engine not installed")

    app = _app(tmp_path, monkeypatch, 59510)
    app.dependency_overrides[get_knowledge_service] = lambda: _FailingKnowledgeService()
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.get("/api/v1/knowledge/kb/metrics", headers=_HEADERS)
        assert r.status_code == 503, r.text
        _assert_envelope(r.json(), "ENGINE_UNAVAILABLE")


# --------------------------------------------------------------------------- #
# End-to-end document flow against the real substrate (markdown passthrough so
# no heavy converter/embedder is booted): ingest → list → get → edit →
# reconvert-blocked → reindex → grep → delete.
# --------------------------------------------------------------------------- #


def test_document_flow_ingest_get_edit_reconvert_reindex_grep(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59520)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        _create_scope(c, "kb", {"retrieval_modes": ["keyword", "grep"]})

        # ingest a markdown doc (converted source_mode)
        ing = c.post(
            "/api/v1/knowledge/kb/documents",
            files={"file": ("notes.md", b"# Title\n\ndeploy via make release\n", "text/markdown")},
            headers=_HEADERS,
        )
        assert ing.status_code == 201, ing.text
        doc = ing.json()
        assert doc["source_mode"] == "converted"
        doc_id = doc["id"]
        # The in-app viewer is read-only: each document carries the absolute
        # path of its normalized markdown + the containing folder so the UI
        # can open-in-external-editor / reveal.
        docs_dir = tmp_path / ".coffer" / "knowledge" / "kb" / "inbox"
        assert doc["path"] == str(docs_dir / f"{doc_id}.md")
        assert doc["folder_path"] == str(docs_dir)

        # list-docs
        listed = c.get("/api/v1/knowledge/kb/documents", headers=_HEADERS)
        assert listed.status_code == 200
        assert listed.json()["total"] == 1
        listed_doc = listed.json()["documents"][0]
        assert listed_doc["path"] == str(docs_dir / f"{doc_id}.md")
        assert listed_doc["folder_path"] == str(docs_dir)

        # read (markdown body)
        got = c.get(f"/api/v1/knowledge/kb/documents/{doc_id}", headers=_HEADERS)
        assert got.status_code == 200
        assert "make release" in got.json()["markdown"]
        assert got.json()["path"] == str(docs_dir / f"{doc_id}.md")
        assert got.json()["folder_path"] == str(docs_dir)

        # edit -> source_mode becomes edited
        ed = c.put(
            f"/api/v1/knowledge/kb/documents/{doc_id}",
            json={"markdown": "# Edited\n\nnow deploys via make ship\n"},
            headers=_HEADERS,
        )
        assert ed.status_code == 200, ed.text
        assert ed.json()["source_mode"] == "edited"

        # reconvert blocked once edited -> 409
        rc = c.post(
            f"/api/v1/knowledge/kb/documents/{doc_id}/reconvert",
            headers=_HEADERS,
        )
        assert rc.status_code == 409, rc.text
        _assert_envelope(rc.json(), "RECONVERSION_BLOCKED")

        # reindex
        ri = c.post("/api/v1/knowledge/kb/reindex", headers=_HEADERS)
        assert ri.status_code == 200, ri.text
        body = ri.json()
        assert set(body) == {
            "documents_scanned",
            "documents_reindexed",
            "documents_skipped",
            "documents_removed",
            "documents_degraded",
        }

        # grep over the markdown files
        gr = c.post(
            "/api/v1/knowledge/kb/grep",
            json={"pattern": "make ship", "max_matches": 10},
            headers=_HEADERS,
        )
        assert gr.status_code == 200, gr.text
        gbody = gr.json()
        assert "truncated" in gbody
        assert isinstance(gbody["hits"], list)

        # delete the doc
        d = c.delete(f"/api/v1/knowledge/kb/documents/{doc_id}", headers=_HEADERS)
        assert d.status_code == 204
        assert c.get("/api/v1/knowledge/kb/documents", headers=_HEADERS).json()["total"] == 0


def test_document_chunk_count_is_real(tmp_path, monkeypatch):
    """``chunk_count`` must carry the document's actual chunk-row count on the
    ingest, list and detail responses — not a hardwired 0 (review finding)."""
    app = _app(tmp_path, monkeypatch, 59530)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        _create_scope(c, "kb", {"retrieval_modes": ["keyword", "grep"]})
        ing = c.post(
            "/api/v1/knowledge/kb/documents",
            files={"file": ("a.md", b"# A\n\nchunky content body\n", "text/markdown")},
            headers=_HEADERS,
        )
        assert ing.status_code == 201, ing.text
        assert ing.json()["chunk_count"] >= 1
        doc_id = ing.json()["id"]

        listed = c.get("/api/v1/knowledge/kb/documents", headers=_HEADERS).json()
        assert listed["documents"][0]["chunk_count"] >= 1

        detail = c.get(f"/api/v1/knowledge/kb/documents/{doc_id}", headers=_HEADERS).json()
        assert detail["chunk_count"] >= 1


def test_documents_ingest_into_the_auto_provisioned_global_scope(tmp_path, monkeypatch):
    """Documents are no longer confined to named collections: ``global`` holds
    both halves and auto-provisions on first document access."""
    app = _app(tmp_path, monkeypatch, 59535)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        ing = c.post(
            "/api/v1/knowledge/global/documents",
            files={"file": ("g.md", b"# G\n\nglobal doc body\n", "text/markdown")},
            headers=_HEADERS,
        )
        assert ing.status_code == 201, ing.text
        listed = c.get("/api/v1/knowledge/global/documents", headers=_HEADERS).json()
        assert listed["total"] == 1


@pytest.mark.acceptance(spec="007-memory", scenario="filter documents by title")
def test_list_documents_filtered_by_title(tmp_path, monkeypatch):
    """``GET /documents?q=`` applies a case-insensitive title substring filter
    server-side BEFORE limit/offset; ``total`` is the filtered count."""
    app = _app(tmp_path, monkeypatch, 59540)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        _create_scope(c, "kb", {"retrieval_modes": ["keyword", "grep"]})
        for fn, md in (
            ("a.md", b"# Quarterly Budget\n\nthe budget body\n"),
            ("b.md", b"# Travel Notes\n\nthe travel body\n"),
            ("c.md", b"# Budget Forecast\n\nthe forecast body\n"),
        ):
            ing = c.post(
                "/api/v1/knowledge/kb/documents",
                files={"file": (fn, md, "text/markdown")},
                headers=_HEADERS,
            )
            assert ing.status_code == 201, ing.text

        # Unfiltered: all three.
        allout = c.get("/api/v1/knowledge/kb/documents", headers=_HEADERS).json()
        assert allout["total"] == 3

        # Filter "budget" → only the two budget docs (case-insensitive: lowercase
        # query matches the title-cased headings).
        filtered = c.get(
            "/api/v1/knowledge/kb/documents",
            params={"q": "budget"},
            headers=_HEADERS,
        ).json()
        titles = sorted(d["title"] for d in filtered["documents"])
        assert titles == ["Budget Forecast", "Quarterly Budget"]
        # total reflects the FILTERED count, not the corpus size.
        assert filtered["total"] == 2

        # Case-insensitivity the other way: uppercase query still matches.
        upper = c.get(
            "/api/v1/knowledge/kb/documents",
            params={"q": "TRAVEL"},
            headers=_HEADERS,
        ).json()
        assert upper["total"] == 1
        assert upper["documents"][0]["title"] == "Travel Notes"


def test_entries_and_documents_share_a_scope_without_leaking_across_lanes(tmp_path, monkeypatch):
    """One scope, one entry, one ingested document — each lane reports only itself.

    After the memory + knowledge_base merge both writers index into ``documents``
    under a single ``(kind, resource_name)``. Nothing in the row said which lane
    it belonged to, so every document read also returned the entries: a scope
    holding one of each reported ``document_count == 2`` and listed the entry as
    a document, with a path (``inbox/<id>.md``) that did not exist — the entry's
    file lives under ``knowledge/inbox/``.

    Asserting the two counts on separate scopes, as the other tests here do,
    cannot catch this. The overlap is the whole point.
    """
    app = _app(tmp_path, monkeypatch, 59545)
    with TestClient(app) as c:
        set_active_token(_TOKEN)

        entry = c.post(
            "/api/v1/knowledge/global/entries",
            json={"title": "an entry", "text": "written through the entry lane"},
            headers=_HEADERS,
        )
        assert entry.status_code == 201, entry.text
        entry_id = entry.json()["id"]

        ing = c.post(
            "/api/v1/knowledge/global/documents",
            files={
                "file": ("d.md", b"# D\n\ningested through the document lane\n", "text/markdown")
            },
            headers=_HEADERS,
        )
        assert ing.status_code == 201, ing.text
        document_id = ing.json()["id"]

        metrics = c.get("/api/v1/knowledge/global/metrics", headers=_HEADERS).json()
        assert metrics["entry_count"] == 1, metrics
        assert metrics["document_count"] == 1, metrics

        listed = c.get("/api/v1/knowledge/global/documents", headers=_HEADERS).json()
        assert listed["total"] == 1, listed
        ids = [d["id"] for d in listed["documents"]]
        assert ids == [document_id], ids
        assert entry_id not in ids

        entries = c.get("/api/v1/knowledge/global/entries", headers=_HEADERS).json()
        entry_ids = [e["id"] for e in entries["entries"]]
        assert entry_ids == [entry_id], entry_ids
        assert document_id not in entry_ids
