"""Integration tests for the async native-memory import-batch routes + overlay.

Builds a minimal app with the native-memory router and a fake batch service +
fake native-memory listing service injected via dependency_overrides (no DB, no
runner).
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient

from coffer.application.agent.native_import_batch import EnqueueResult
from coffer.application.async_ops.registry import InflightEntry, OpState
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.agent_native_memory_routes import router as native_router
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import (
    get_agent_native_memory_service,
    get_native_import_batch_service,
    get_native_import_batch_service_optional,
)

_HEADERS = {"X-Coffer-Token": "t"}


@dataclass(frozen=True)
class _Store:
    project_label: str
    project_path: str | None
    memory_dir: str
    item_count: int


_STORE = _Store(
    project_label="demo",
    project_path="/home/user/repo",
    memory_dir="/home/user/.claude/projects/x/memory",
    item_count=3,
)


class _FakeNativeService:
    async def list_stores(self, _agent: str) -> list[_Store]:
        return [_STORE]


class _FakeBatch:
    def __init__(self, *, inflight: dict[str, InflightEntry] | None = None) -> None:
        self._inflight = inflight or {}
        self.last_enqueue_imports: list[str] | None = None

    def inflight(self, _agent: str) -> dict[str, InflightEntry]:
        return self._inflight

    def enqueue_imports(self, _agent: str, memory_dirs: list[str]) -> EnqueueResult:
        self.last_enqueue_imports = memory_dirs
        return EnqueueResult(queued=len(memory_dirs), total=len(memory_dirs))


def _app(batch: _FakeBatch) -> FastAPI:
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(native_router)
    app.dependency_overrides[get_agent_native_memory_service] = _FakeNativeService
    app.dependency_overrides[get_native_import_batch_service] = lambda: batch
    app.dependency_overrides[get_native_import_batch_service_optional] = lambda: batch
    app.dependency_overrides[require_token] = lambda: None
    return app


def test_list_overlays_inflight_import_status() -> None:
    batch = _FakeBatch(inflight={_STORE.memory_dir: InflightEntry(OpState.running)})
    with TestClient(_app(batch)) as c:
        r = c.get("/api/v1/agents/a/native-memory", headers=_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["import_status"] == "running"


def test_list_no_inflight_status_is_null() -> None:
    batch = _FakeBatch()
    with TestClient(_app(batch)) as c:
        r = c.get("/api/v1/agents/a/native-memory", headers=_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["import_status"] is None


def test_import_batch_returns_counts_and_202() -> None:
    batch = _FakeBatch()
    with TestClient(_app(batch)) as c:
        r = c.post(
            "/api/v1/agents/a/native-memory/import-batch",
            json={"memory_dirs": ["/d1", "/d2"]},
            headers=_HEADERS,
        )
    assert r.status_code == 202, r.text
    assert r.json() == {"queued": 2, "total": 2}
    assert batch.last_enqueue_imports == ["/d1", "/d2"]


def test_import_batch_empty_body_enqueues_nothing() -> None:
    batch = _FakeBatch()
    with TestClient(_app(batch)) as c:
        r = c.post(
            "/api/v1/agents/a/native-memory/import-batch",
            json={},
            headers=_HEADERS,
        )
    assert r.status_code == 202, r.text
    assert r.json() == {"queued": 0, "total": 0}
    assert batch.last_enqueue_imports == []


def test_import_status_lists_inflight() -> None:
    batch = _FakeBatch(
        inflight={
            "/d1": InflightEntry(OpState.running),
            "/d2": InflightEntry(OpState.error, "boom"),
        }
    )
    with TestClient(_app(batch)) as c:
        r = c.get("/api/v1/agents/a/native-memory/import-status", headers=_HEADERS)
    assert r.status_code == 200, r.text
    by_dir = {s["memory_dir"]: s for s in r.json()["statuses"]}
    assert by_dir["/d1"]["state"] == "running"
    assert by_dir["/d2"]["state"] == "error"
    assert by_dir["/d2"]["message"] == "boom"
