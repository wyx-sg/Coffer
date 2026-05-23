"""HTTP-level tests for /api/v1/memory_stores/* — error envelope + route logic.

The memory lifecycle is covered against a fake store in
test_memory_lifecycle.py. This file pins the *route* layer: the standard
{error:{code,message,details}} envelope and status codes. It exercises
error paths the service raises before reaching the store (no real mem0)
plus the happy-path of every verb against a stubbed MemoryService
(TEST26-017).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from starlette.testclient import TestClient

from coffer.domain.errors import EngineUnavailable, MemoryNotFound, MemoryRejected
from coffer.domain.memory.record import MemoryRecord
from coffer.domain.memory.store import MemoryHit
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_memory_service

_TOKEN = "memory-routes-token"
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


def test_get_missing_store_returns_not_found_envelope(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59470)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.get("/api/v1/memory_stores/nope", headers=_HEADERS)
        assert r.status_code == 404
        _assert_envelope(r.json(), "MEMORY_STORE_NOT_FOUND")


def test_create_and_list_store(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59480)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post(
            "/api/v1/memory_stores",
            json={"name": "prefs", "config": {}},
            headers=_HEADERS,
        )
        assert r.status_code == 201, r.text
        assert r.json()["name"] == "prefs"

        listed = c.get("/api/v1/memory_stores", headers=_HEADERS)
        assert listed.status_code == 200
        assert any(s["name"] == "prefs" for s in listed.json()["memory_stores"])


@pytest.mark.acceptance(
    spec="007-memory",
    scenario="add_memory returns 503 when LLM provider is none",
)
def test_add_memory_without_llm_returns_envelope(tmp_path, monkeypatch):
    """A store with llm_provider='none' cannot accept writes — the service
    raises LLMNotConfigured before the mem0 engine is ever opened."""
    app = _app(tmp_path, monkeypatch, 59490)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        c.post(
            "/api/v1/memory_stores",
            json={"name": "store", "config": {}},
            headers=_HEADERS,
        )
        r = c.post(
            "/api/v1/memory_stores/store/memories",
            json={"text": "the user prefers tabs"},
            headers=_HEADERS,
        )
        assert r.status_code == 503, r.text
        _assert_envelope(r.json(), "LLM_NOT_CONFIGURED")


@pytest.mark.acceptance(
    spec="007-memory",
    scenario="memory text exceeding bound is rejected",
)
def test_add_too_long_memory_returns_rejected_envelope(tmp_path, monkeypatch):
    """Text over the store's max_memory_chars is rejected with reason."""
    app = _app(tmp_path, monkeypatch, 59500)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        c.post(
            "/api/v1/memory_stores",
            json={"name": "small", "config": {"max_memory_chars": 64}},
            headers=_HEADERS,
        )
        r = c.post(
            "/api/v1/memory_stores/small/memories",
            json={"text": "x" * 200},
            headers=_HEADERS,
        )
        assert r.status_code == 400, r.text
        body = r.json()
        _assert_envelope(body, "MEMORY_REJECTED")
        assert body["error"]["details"]["reason"] == "too_long"


def test_get_missing_memory_returns_envelope(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59510)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        c.post("/api/v1/memory_stores", json={"name": "store", "config": {}}, headers=_HEADERS)
        r = c.get("/api/v1/memory_stores/store/memories/nope", headers=_HEADERS)
        assert r.status_code == 404
        _assert_envelope(r.json(), "MEMORY_NOT_FOUND")


def test_delete_memory_returns_bodyless_204(tmp_path, monkeypatch):
    """A successful memory delete returns a bodyless 204. The memory service
    is faked so the route is exercised without a real mem0 engine."""

    class _FakeMemoryService:
        def __init__(self) -> None:
            self.deleted: list[tuple[str, str]] = []

        async def delete(self, *, store_name: str, memory_id: str, actor: str) -> None:
            self.deleted.append((store_name, memory_id))

    fake = _FakeMemoryService()
    app = _app(tmp_path, monkeypatch, 59520)
    app.dependency_overrides[get_memory_service] = lambda: fake
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.delete("/api/v1/memory_stores/store/memories/m1", headers=_HEADERS)
        assert r.status_code == 204, r.text
        assert r.content == b""
    assert fake.deleted == [("store", "m1")]


# ---------------------------------------------------------------------------
# TEST26-017 — happy-path route tests with a stubbed MemoryService.
#
# The error-envelope tests above exercise the failure paths that the real
# service raises before mem0 ever opens. These pin the *route layer* against
# a fake service: response shape, status codes, body coercion, query
# clamping. No real mem0/LLM is involved.
# ---------------------------------------------------------------------------


class _StubMemoryService:
    """Minimal stand-in. Records each call so assertions can verify the
    route forwarded the right arguments."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        # Override these dicts in a test to inject errors.
        self.behavior: dict[str, BaseException] = {}

    def _maybe_raise(self, key: str) -> None:
        exc = self.behavior.get(key)
        if exc is not None:
            raise exc

    async def add(self, *, store_name: str, text: str, actor: str) -> MemoryRecord:
        self.calls.append(("add", {"store_name": store_name, "text": text, "actor": actor}))
        self._maybe_raise("add")
        now = datetime.now(tz=UTC)
        return MemoryRecord(
            id="m-1",
            store_name=store_name,
            text=text,
            actor=actor,  # type: ignore[arg-type]
            created_at=now,
            updated_at=now,
        )

    async def list_memories(
        self, *, store_name: str, limit: int, offset: int
    ) -> tuple[list[MemoryRecord], int]:
        self.calls.append(
            ("list_memories", {"store_name": store_name, "limit": limit, "offset": offset})
        )
        self._maybe_raise("list_memories")
        now = datetime.now(tz=UTC)
        return (
            [
                MemoryRecord(
                    id="m-1",
                    store_name=store_name,
                    text="hello",
                    actor="user",
                    created_at=now,
                    updated_at=now,
                ),
            ],
            1,
        )

    async def update(
        self, *, store_name: str, memory_id: str, new_text: str, actor: str
    ) -> MemoryRecord:
        self.calls.append(
            (
                "update",
                {
                    "store_name": store_name,
                    "memory_id": memory_id,
                    "new_text": new_text,
                    "actor": actor,
                },
            )
        )
        self._maybe_raise("update")
        now = datetime.now(tz=UTC)
        return MemoryRecord(
            id=memory_id,
            store_name=store_name,
            text=new_text,
            actor=actor,  # type: ignore[arg-type]
            created_at=now,
            updated_at=now,
        )

    async def clear(self, *, store_name: str, actor: str) -> int:
        self.calls.append(("clear", {"store_name": store_name, "actor": actor}))
        self._maybe_raise("clear")
        return 3

    async def search(self, *, store_name: str, query: str, top_k: int) -> list[MemoryHit]:
        self.calls.append(("search", {"store_name": store_name, "query": query, "top_k": top_k}))
        self._maybe_raise("search")
        return [
            MemoryHit(id="m-1", text="hello world", score=0.9, created_at=datetime.now(tz=UTC)),
        ]

    async def metrics(self, *, store_name: str) -> tuple[int, int]:
        self.calls.append(("metrics", {"store_name": store_name}))
        self._maybe_raise("metrics")
        return 7, 1234


def _app_with_stub(tmp_path, monkeypatch, port_start: int):
    app = _app(tmp_path, monkeypatch, port_start)
    stub = _StubMemoryService()
    app.dependency_overrides[get_memory_service] = lambda: stub
    return app, stub


def test_add_memory_returns_201(tmp_path, monkeypatch):
    app, stub = _app_with_stub(tmp_path, monkeypatch, 59530)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post(
            "/api/v1/memory_stores/s1/memories",
            json={"text": "the user prefers tabs"},
            headers={**_HEADERS, "X-Coffer-Actor": "user"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["id"] == "m-1"
        assert body["text"] == "the user prefers tabs"
        assert body["actor"] == "user"
    # The route forwarded store_name + actor unchanged.
    assert stub.calls[0][1]["store_name"] == "s1"
    assert stub.calls[0][1]["actor"] == "user"


def test_list_memories_paginates_and_returns_total(tmp_path, monkeypatch):
    app, stub = _app_with_stub(tmp_path, monkeypatch, 59540)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.get(
            "/api/v1/memory_stores/s1/memories?limit=10&offset=5",
            headers=_HEADERS,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 1
        assert len(body["memories"]) == 1
    assert stub.calls[0] == ("list_memories", {"store_name": "s1", "limit": 10, "offset": 5})


def test_update_memory_returns_new_text(tmp_path, monkeypatch):
    app, _stub = _app_with_stub(tmp_path, monkeypatch, 59550)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.patch(
            "/api/v1/memory_stores/s1/memories/m-1",
            json={"text": "the user prefers spaces now"},
            headers={**_HEADERS, "X-Coffer-Actor": "user"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["text"] == "the user prefers spaces now"


def test_clear_memories_returns_count(tmp_path, monkeypatch):
    app, _stub = _app_with_stub(tmp_path, monkeypatch, 59560)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post("/api/v1/memory_stores/s1/memories/clear", headers=_HEADERS)
        assert r.status_code == 200, r.text
        assert r.json() == {"cleared": 3}


def test_search_memory_boundary_top_k_1(tmp_path, monkeypatch):
    app, stub = _app_with_stub(tmp_path, monkeypatch, 59570)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post(
            "/api/v1/memory_stores/s1/search",
            json={"query": "tabs", "top_k": 1},
            headers=_HEADERS,
        )
        assert r.status_code == 200, r.text
        hits = r.json()["hits"]
        assert len(hits) == 1
    assert stub.calls[0][1]["top_k"] == 1


def test_search_memory_boundary_top_k_20(tmp_path, monkeypatch):
    app, stub = _app_with_stub(tmp_path, monkeypatch, 59580)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post(
            "/api/v1/memory_stores/s1/search",
            json={"query": "tabs", "top_k": 20},
            headers=_HEADERS,
        )
        assert r.status_code == 200, r.text
    assert stub.calls[0][1]["top_k"] == 20


def test_search_memory_top_k_above_20_rejected_by_schema(tmp_path, monkeypatch):
    """top_k > 20 is rejected by the FastAPI schema (Pydantic le=20)."""
    app, _stub = _app_with_stub(tmp_path, monkeypatch, 59590)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post(
            "/api/v1/memory_stores/s1/search",
            json={"query": "tabs", "top_k": 21},
            headers=_HEADERS,
        )
        assert r.status_code == 422, r.text


def test_metrics_returns_count_and_disk_bytes(tmp_path, monkeypatch):
    app, _stub = _app_with_stub(tmp_path, monkeypatch, 59600)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.get("/api/v1/memory_stores/s1/metrics", headers=_HEADERS)
        assert r.status_code == 200, r.text
        assert r.json() == {"memory_count": 7, "disk_bytes": 1234}


# ---------------------------------------------------------------------------
# TEST26-010 — edge-case acceptance tests.
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="007-memory",
    scenario="add_memory surfaces upstream LLM error without corrupting store",
)
def test_add_memory_with_llm_unreachable_returns_503(tmp_path, monkeypatch):
    """If the LLM engine is unreachable mid-write, the route surfaces a 503
    `engine_unavailable` envelope. The fake service simulates the upstream
    failure; no real mem0 needed."""
    app, stub = _app_with_stub(tmp_path, monkeypatch, 59610)
    stub.behavior["add"] = EngineUnavailable("mem0", "connection refused")
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post(
            "/api/v1/memory_stores/s1/memories",
            json={"text": "the user prefers tabs"},
            headers=_HEADERS,
        )
        assert r.status_code == 503, r.text
        body = r.json()
        _assert_envelope(body, "ENGINE_UNAVAILABLE")
    # Recovery: clear the fault, a subsequent add succeeds (no corruption).
    stub.behavior.pop("add")
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post(
            "/api/v1/memory_stores/s1/memories",
            json={"text": "follow-up succeeds"},
            headers=_HEADERS,
        )
        assert r.status_code == 201, r.text


@pytest.mark.acceptance(spec="007-memory", scenario="empty memory text is rejected")
def test_add_empty_memory_rejected_by_schema(tmp_path, monkeypatch):
    """Empty/whitespace text is rejected at the FastAPI schema layer with
    422 (Pydantic min_length=1). No service call happens."""
    app, stub = _app_with_stub(tmp_path, monkeypatch, 59620)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post(
            "/api/v1/memory_stores/s1/memories",
            json={"text": ""},
            headers=_HEADERS,
        )
        assert r.status_code == 422, r.text
    assert stub.calls == []  # service never invoked


@pytest.mark.acceptance(spec="007-memory", scenario="empty memory text is rejected")
def test_add_whitespace_memory_rejected_with_envelope(tmp_path, monkeypatch):
    """Whitespace-only text passes the min_length=1 schema check but is
    rejected by the service with ``MEMORY_REJECTED { reason: 'empty' }``."""
    app, stub = _app_with_stub(tmp_path, monkeypatch, 59630)
    stub.behavior["add"] = MemoryRejected("empty", "memory text is empty")
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post(
            "/api/v1/memory_stores/s1/memories",
            json={"text": "   "},
            headers=_HEADERS,
        )
        assert r.status_code == 400, r.text
        body = r.json()
        _assert_envelope(body, "MEMORY_REJECTED")
        assert body["error"]["details"]["reason"] == "empty"


# ---------------------------------------------------------------------------
# TEST26-010 — Embedding model swap rejected.
# Depends on CODE26-003: ``make_memory_kind`` wires an ``on_update_config``
# hook that rejects changes to ``embedding_model`` and the other
# immutable fields. We test against the real resource service rather than
# the fake memory service because the gate lives in the kind/resource layer.
# ---------------------------------------------------------------------------


def test_update_store_embedding_model_rejected(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59640)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post(
            "/api/v1/memory_stores",
            json={
                "name": "immut",
                "config": {"embedding_model": "BAAI/bge-small-en-v1.5"},
            },
            headers=_HEADERS,
        )
        assert r.status_code == 201, r.text
        # Try to PATCH the embedding_model via the kind-agnostic resource
        # update endpoint. The kind's on_update_config hook rejects it.
        r = c.patch(
            "/api/v1/resources/memory/immut",
            json={"config": {"embedding_model": "other/model"}},
            headers=_HEADERS,
        )
        # CODE26-003 returns 422 ConfigValidationError; mirrors the
        # knowledge_base hook pattern. The error message names the immutable
        # field so a follow-up UI surface can render a clear diagnostic.
        assert r.status_code == 422, r.text
        body = r.json()
        assert body["error"]["code"] == "CONFIG_INVALID"
        assert "embedding_model" in body["error"]["message"].lower()


def test_update_memory_with_too_long_text_returns_envelope(tmp_path, monkeypatch):
    """Spec scenario "memory text exceeding bound is rejected" — verified
    here against the *update* path. The add-path version already lives at
    test_add_too_long_memory_returns_rejected_envelope above."""
    app, stub = _app_with_stub(tmp_path, monkeypatch, 59650)
    stub.behavior["update"] = MemoryRejected("too_long", "text too long")
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.patch(
            "/api/v1/memory_stores/s1/memories/m-1",
            json={"text": "x"},  # length passes schema; service rejects
            headers=_HEADERS,
        )
        assert r.status_code == 400, r.text
        body = r.json()
        _assert_envelope(body, "MEMORY_REJECTED")
        assert body["error"]["details"]["reason"] == "too_long"


def test_update_memory_not_found_returns_envelope(tmp_path, monkeypatch):
    """The MemoryNotFound domain error maps to a 404 with a MEMORY_NOT_FOUND
    envelope when a non-existent memory id is patched."""
    app, stub = _app_with_stub(tmp_path, monkeypatch, 59660)
    stub.behavior["update"] = MemoryNotFound("s1", "ghost")
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.patch(
            "/api/v1/memory_stores/s1/memories/ghost",
            json={"text": "x"},
            headers=_HEADERS,
        )
        assert r.status_code == 404, r.text
        _assert_envelope(r.json(), "MEMORY_NOT_FOUND")
