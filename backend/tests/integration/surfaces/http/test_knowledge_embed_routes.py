"""HTTP-level tests for the async document re-embed slice.

Covers the endpoints (GET /documents/status, POST /documents/reembed-batch)
and the per-document ``embed_status`` overlay on the documents list/detail. The
batch service is wired manually against the real knowledge service (app.py wires
it in production via the async-batch wiring); the ``_optional`` overlay means the
existing list/get endpoints degrade to ``embed_status=None`` when it is absent.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from coffer.application.async_ops.registry import AsyncOpRegistry
from coffer.application.async_ops.runner import AsyncOpRunner
from coffer.application.knowledge.batch import KnowledgeBaseBatchService
from coffer.domain.knowledge.document import DOCUMENT_SCAN_LIMIT
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_knowledge_service
from coffer.surfaces.http.knowledge import batch_state

_TOKEN = "knowledge-embed-token"
_HEADERS = {"X-Coffer-Token": _TOKEN}


def _app(tmp_path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    return create_app()


def _wire_batch() -> None:
    """Build + register the batch service against the live knowledge service."""
    svc = get_knowledge_service()
    registry = AsyncOpRegistry()
    runner = AsyncOpRunner(registry, concurrency=1)  # enqueue-only; not started

    async def list_documents(scope_name: str):
        docs, _total = await svc.list_documents(
            scope_name=scope_name, limit=DOCUMENT_SCAN_LIMIT, offset=0
        )
        return docs

    async def reembed(scope_name: str, document_id: str) -> None:
        await svc.reembed_document(scope_name=scope_name, document_id=document_id)

    batch_state.set_batch_service(
        KnowledgeBaseBatchService(
            runner=runner,
            registry=registry,
            list_documents=list_documents,
            reembed=reembed,
        )
    )


@pytest.fixture(autouse=True)
def _reset_batch_state():
    yield
    batch_state.set_batch_service(None)


def _create_scope_with_doc(c: TestClient) -> str:
    c.post("/api/v1/knowledge", json={"name": "kb", "config": {}}, headers=_HEADERS)
    r = c.post(
        "/api/v1/knowledge/kb/documents",
        files={"file": ("a.md", b"# A\n\nalpha body\n", "text/markdown")},
        headers=_HEADERS,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_list_embed_status_done_when_no_embedder(tmp_path, monkeypatch):
    """With no embedding provider the doc is not pending → derived status 'done'."""
    app = _app(tmp_path, monkeypatch, 59700)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        _wire_batch()
        _create_scope_with_doc(c)
        listed = c.get("/api/v1/knowledge/kb/documents", headers=_HEADERS).json()
        assert listed["documents"][0]["embed_status"] == "done"


def test_list_embed_status_none_when_batch_unwired(tmp_path, monkeypatch):
    """Without the batch service the overlay degrades to embed_status=None."""
    app = _app(tmp_path, monkeypatch, 59710)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        _create_scope_with_doc(c)
        # App startup wires the batch service; unwire it here to exercise the
        # _optional graceful-degradation path (embed_status=None).
        batch_state.set_batch_service(None)
        listed = c.get("/api/v1/knowledge/kb/documents", headers=_HEADERS).json()
        assert listed["documents"][0]["embed_status"] is None


def test_documents_status_empty_when_nothing_in_flight(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59720)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        _wire_batch()
        _create_scope_with_doc(c)
        r = c.get("/api/v1/knowledge/kb/documents/status", headers=_HEADERS)
        assert r.status_code == 200
        assert r.json() == {"statuses": []}


def test_reembed_batch_skips_already_embedded(tmp_path, monkeypatch):
    """A doc with no pending embed is skipped (nothing to retry) → 202 with skipped."""
    app = _app(tmp_path, monkeypatch, 59730)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        _wire_batch()
        _create_scope_with_doc(c)
        r = c.post(
            "/api/v1/knowledge/kb/documents/reembed-batch",
            json={"all": True},
            headers=_HEADERS,
        )
        assert r.status_code == 202, r.text
        body = r.json()
        assert body == {"queued": 0, "skipped": 1, "total": 1}


def test_reembed_batch_requires_batch_service(tmp_path, monkeypatch):
    """Without the batch service the 202 endpoint raises (service not initialised)."""
    app = _app(tmp_path, monkeypatch, 59740)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        _create_scope_with_doc(c)
        # App startup wires the batch service; unwire it to assert the 202 batch
        # endpoint requires it.
        batch_state.set_batch_service(None)
        with pytest.raises(RuntimeError):
            c.post(
                "/api/v1/knowledge/kb/documents/reembed-batch",
                json={"all": True},
                headers=_HEADERS,
            )
