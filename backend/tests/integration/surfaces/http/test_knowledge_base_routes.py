"""HTTP-level tests for /api/v1/knowledge_bases/* — error envelope + route logic.

The KB lifecycle is covered against a fake store in test_kb_lifecycle.py.
This file pins the *route* layer: the standard {error:{code,message,details}}
envelope, status codes, and the upload size guard. It deliberately avoids
the ingest/search success paths so the real LlamaIndex engine is never
loaded — every case here is rejected before the store is touched.
"""

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_TOKEN = "kb-routes-token"
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


def test_get_missing_kb_returns_kb_not_found_envelope(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59400)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.get("/api/v1/knowledge_bases/nope", headers=_HEADERS)
        assert r.status_code == 404
        # ResourceNotFound is translated to the kind-specific code.
        _assert_envelope(r.json(), "KB_NOT_FOUND")


def test_create_and_list_kb(tmp_path, monkeypatch):
    # NB: TEST22-009 — the "agent lists available knowledge bases" acceptance
    # marker lives on the MCP-tool-level test (test_builtin_tools.py), not
    # on this HTTP-route test. Agents see KBs through the coffer__ tool, not
    # via the HTTP API.
    app = _app(tmp_path, monkeypatch, 59410)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post(
            "/api/v1/knowledge_bases",
            json={"name": "designs", "config": {}},
            headers=_HEADERS,
        )
        assert r.status_code == 201, r.text
        assert r.json()["name"] == "designs"

        listed = c.get("/api/v1/knowledge_bases", headers=_HEADERS)
        assert listed.status_code == 200
        assert any(k["name"] == "designs" for k in listed.json()["knowledge_bases"])


def test_create_duplicate_kb_returns_conflict_envelope(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59420)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        body = {"name": "dup", "config": {}}
        assert c.post("/api/v1/knowledge_bases", json=body, headers=_HEADERS).status_code == 201
        r = c.post("/api/v1/knowledge_bases", json=body, headers=_HEADERS)
        assert r.status_code == 409
        _assert_envelope(r.json(), "RESOURCE_ALREADY_EXISTS")


def test_oversized_upload_rejected_with_413_envelope(tmp_path, monkeypatch):
    """The per-KB max_document_bytes limit yields 413 with reason=too_large."""
    app = _app(tmp_path, monkeypatch, 59430)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        c.post(
            "/api/v1/knowledge_bases",
            json={"name": "tiny", "config": {"max_document_bytes": 1024}},
            headers=_HEADERS,
        )
        r = c.post(
            "/api/v1/knowledge_bases/tiny/documents",
            files={"file": ("big.md", b"x" * 4096, "text/plain")},
            headers=_HEADERS,
        )
        assert r.status_code == 413, r.text
        body = r.json()
        _assert_envelope(body, "INGEST_REJECTED")
        assert body["error"]["details"]["reason"] == "too_large"


def test_upload_route_guard_rejects_before_buffering(tmp_path, monkeypatch):
    """The absolute-ceiling guard in the route rejects an oversized upload
    via file.size. The KB's own limit (25 MB default) is far larger than the
    payload, so a 413 here can only come from the route-level guard."""
    from coffer.surfaces.http.knowledge_base import routes as kb_routes

    monkeypatch.setattr(kb_routes, "_ABSOLUTE_MAX_DOC_BYTES", 64)
    app = _app(tmp_path, monkeypatch, 59440)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        c.post(
            "/api/v1/knowledge_bases",
            json={"name": "kb", "config": {}},
            headers=_HEADERS,
        )
        r = c.post(
            "/api/v1/knowledge_bases/kb/documents",
            files={"file": ("big.md", b"x" * 256, "text/plain")},
            headers=_HEADERS,
        )
        assert r.status_code == 413, r.text
        _assert_envelope(r.json(), "INGEST_REJECTED")


def test_get_missing_document_returns_envelope(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59450)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        c.post("/api/v1/knowledge_bases", json={"name": "kb", "config": {}}, headers=_HEADERS)
        r = c.get("/api/v1/knowledge_bases/kb/documents/nope", headers=_HEADERS)
        assert r.status_code == 404
        _assert_envelope(r.json(), "DOCUMENT_NOT_FOUND")


def test_delete_document_returns_bodyless_204(tmp_path, monkeypatch):
    """A successful document delete returns a bodyless 204. The KB service is
    faked so the route is exercised without a real ingested document."""
    from coffer.surfaces.http.dependencies import get_kb_service

    class _FakeKbService:
        def __init__(self) -> None:
            self.deleted: list[tuple[str, str]] = []

        async def delete_document(self, *, kb_name: str, document_id: str, actor: str) -> None:
            self.deleted.append((kb_name, document_id))

    fake = _FakeKbService()
    app = _app(tmp_path, monkeypatch, 59460)
    app.dependency_overrides[get_kb_service] = lambda: fake
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.delete("/api/v1/knowledge_bases/kb/documents/d1", headers=_HEADERS)
        assert r.status_code == 204, r.text
        assert r.content == b""
    assert fake.deleted == [("kb", "d1")]


# --------------------------------------------------------------------------- #
# TEST22-016 — search + metrics routes coverage
# --------------------------------------------------------------------------- #


class _SearchMetricsFakeKbService:
    """Fake KB service that returns canned passages + metrics so the route
    layer is exercised without booting the converter/embedder or writing docs.

    Matches the spec-006 service contract: ``search`` takes ``mode`` and returns
    a ``SearchResult``; ``metrics`` returns a dict."""

    def __init__(self) -> None:
        self.searches: list[tuple[str, str, int]] = []
        self.metrics_calls: list[str] = []

    async def search(self, *, kb_name: str, query: str, top_k: int, mode=None):
        from coffer.domain.knowledge.retrieval import Passage, SearchResult

        self.searches.append((kb_name, query, top_k))
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

    async def metrics(self, *, kb_name: str) -> dict[str, object]:
        self.metrics_calls.append(kb_name)
        return {
            "document_count": 7,
            "chunk_count": 21,
            "disk_bytes": 12345,
            "enabled_modes": ["keyword", "grep"],
        }


def test_search_route_returns_ranked_hits(tmp_path, monkeypatch):
    """TEST22-016: POST /search → 200 with the SearchResponse envelope."""
    from coffer.surfaces.http.dependencies import get_kb_service

    fake = _SearchMetricsFakeKbService()
    app = _app(tmp_path, monkeypatch, 59470)
    app.dependency_overrides[get_kb_service] = lambda: fake
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        # The KB doesn't need to exist on the resource_service when the
        # kb_service is fully faked — the route forwards directly to it.
        r = c.post(
            "/api/v1/knowledge_bases/kb/search",
            json={"query": "tabs", "top_k": 2},
            headers=_HEADERS,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["mode"] == "keyword"
        assert body["fallback"] is None
        assert isinstance(body["passages"], list)
        assert len(body["passages"]) == 2
        hit = body["passages"][0]
        assert set(hit.keys()) >= {"text", "document_id", "title", "score", "position"}
        assert hit["title"] == "prefs.md"
        assert hit["score"] == pytest.approx(0.91)
    assert fake.searches == [("kb", "tabs", 2)]


def test_metrics_route_returns_kb_metrics(tmp_path, monkeypatch):
    """TEST22-016: GET /metrics → 200 with counts + indexed_modes + disk_bytes."""
    from coffer.surfaces.http.dependencies import get_kb_service

    fake = _SearchMetricsFakeKbService()
    app = _app(tmp_path, monkeypatch, 59480)
    app.dependency_overrides[get_kb_service] = lambda: fake
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.get("/api/v1/knowledge_bases/kb/metrics", headers=_HEADERS)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body == {
            "document_count": 7,
            "chunk_count": 21,
            "indexed_modes": ["keyword", "grep"],
            "disk_bytes": 12345,
        }
    assert fake.metrics_calls == ["kb"]


# --------------------------------------------------------------------------- #
# TEST22-012 — top_k validation boundaries
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("top_k", [0, 21, -1, 100])
def test_search_top_k_out_of_range_422(tmp_path, monkeypatch, top_k):
    """TEST22-012: ``top_k`` outside [1, 20] is rejected by the route's
    Pydantic schema as 422, never reaches the KB service."""
    from coffer.surfaces.http.dependencies import get_kb_service

    fake = _SearchMetricsFakeKbService()
    app = _app(tmp_path, monkeypatch, 59490 + abs(top_k) % 5)
    app.dependency_overrides[get_kb_service] = lambda: fake
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post(
            "/api/v1/knowledge_bases/kb/search",
            json={"query": "tabs", "top_k": top_k},
            headers=_HEADERS,
        )
        assert r.status_code == 422, r.text
    assert fake.searches == []  # service never called


# --------------------------------------------------------------------------- #
# TEST22-020 — engine unavailable 503 on search
# --------------------------------------------------------------------------- #


def test_search_engine_unavailable_returns_503(tmp_path, monkeypatch):
    """TEST22-020: a store that raises ``EngineUnavailable`` surfaces as
    HTTP 503 with ``error.code == "ENGINE_UNAVAILABLE"``."""
    from coffer.domain.errors import EngineUnavailable
    from coffer.surfaces.http.dependencies import get_kb_service

    class _FailingKbService:
        async def search(self, *, kb_name: str, query: str, top_k: int, mode=None):
            raise EngineUnavailable(
                "embedding",
                "test: engine not installed",
            )

    app = _app(tmp_path, monkeypatch, 59500)
    app.dependency_overrides[get_kb_service] = lambda: _FailingKbService()
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post(
            "/api/v1/knowledge_bases/kb/search",
            json={"query": "anything", "top_k": 3},
            headers=_HEADERS,
        )
        assert r.status_code == 503, r.text
        _assert_envelope(r.json(), "ENGINE_UNAVAILABLE")


def test_metrics_engine_unavailable_returns_503(tmp_path, monkeypatch):
    """Companion: metrics also surfaces EngineUnavailable through the app-
    wide error handler (the surface treats it uniformly)."""
    from coffer.domain.errors import EngineUnavailable
    from coffer.surfaces.http.dependencies import get_kb_service

    class _FailingKbService:
        async def metrics(self, *, kb_name: str) -> dict[str, object]:
            raise EngineUnavailable("embedding", "test: engine not installed")

    app = _app(tmp_path, monkeypatch, 59510)
    app.dependency_overrides[get_kb_service] = lambda: _FailingKbService()
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.get("/api/v1/knowledge_bases/kb/metrics", headers=_HEADERS)
        assert r.status_code == 503, r.text
        _assert_envelope(r.json(), "ENGINE_UNAVAILABLE")


# --------------------------------------------------------------------------- #
# End-to-end document flow against the real substrate (markdown passthrough so
# no heavy converter/embedder is booted): ingest → list → get → edit →
# reconvert-blocked → reindex → grep → delete.
# --------------------------------------------------------------------------- #


def _create_kb(c, name: str) -> None:
    r = c.post(
        "/api/v1/knowledge_bases",
        json={"name": name, "config": {"enabled_modes": ["keyword", "grep"]}},
        headers=_HEADERS,
    )
    assert r.status_code == 201, r.text


def test_document_flow_ingest_get_edit_reconvert_reindex_grep(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59520)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        _create_kb(c, "kb")

        # ingest a markdown doc (converted source_mode)
        ing = c.post(
            "/api/v1/knowledge_bases/kb/documents",
            files={"file": ("notes.md", b"# Title\n\ndeploy via make release\n", "text/markdown")},
            headers=_HEADERS,
        )
        assert ing.status_code == 201, ing.text
        doc = ing.json()
        assert doc["source_mode"] == "converted"
        doc_id = doc["id"]

        # list-docs
        listed = c.get("/api/v1/knowledge_bases/kb/documents", headers=_HEADERS)
        assert listed.status_code == 200
        assert listed.json()["total"] == 1

        # get-doc (markdown body)
        got = c.get(f"/api/v1/knowledge_bases/kb/documents/{doc_id}", headers=_HEADERS)
        assert got.status_code == 200
        assert "make release" in got.json()["markdown"]

        # edit -> source_mode becomes edited
        ed = c.put(
            f"/api/v1/knowledge_bases/kb/documents/{doc_id}",
            json={"markdown": "# Edited\n\nnow deploys via make ship\n"},
            headers=_HEADERS,
        )
        assert ed.status_code == 200, ed.text
        assert ed.json()["source_mode"] == "edited"

        # reconvert blocked once edited -> 409
        rc = c.post(
            f"/api/v1/knowledge_bases/kb/documents/{doc_id}/reconvert",
            headers=_HEADERS,
        )
        assert rc.status_code == 409, rc.text
        _assert_envelope(rc.json(), "RECONVERSION_BLOCKED")

        # reindex
        ri = c.post("/api/v1/knowledge_bases/kb/reindex", headers=_HEADERS)
        assert ri.status_code == 200, ri.text
        body = ri.json()
        assert set(body) == {
            "documents_scanned",
            "documents_reindexed",
            "documents_skipped",
        }

        # grep over the markdown files
        gr = c.post(
            "/api/v1/knowledge_bases/kb/grep",
            json={"pattern": "make ship", "max_matches": 10},
            headers=_HEADERS,
        )
        assert gr.status_code == 200, gr.text
        gbody = gr.json()
        assert "truncated" in gbody
        assert isinstance(gbody["hits"], list)

        # delete the doc
        d = c.delete(f"/api/v1/knowledge_bases/kb/documents/{doc_id}", headers=_HEADERS)
        assert d.status_code == 204
        assert c.get("/api/v1/knowledge_bases/kb/documents", headers=_HEADERS).json()["total"] == 0
