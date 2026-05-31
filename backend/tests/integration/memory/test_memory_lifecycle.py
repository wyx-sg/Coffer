"""End-to-end lifecycle of the memory kind using FakeMemoryStore."""

from __future__ import annotations

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.memory.kind import make_memory_kind
from coffer.application.memory.service import MemoryService
from coffer.application.resource_service import ResourceService
from coffer.domain.errors import (
    LLMNotConfigured,
    MemoryNotFound,
    MemoryRejected,
)
from coffer.domain.memory.config import MemoryStoreConfig
from coffer.infrastructure.memory.paths import memory_store_dir
from coffer.infrastructure.memory.persistence import (
    SqlAlchemyMemoryRecordRepo,
)
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from tests.integration.memory.fakes import FakeMemoryStore


async def _services(tmp_path, monkeypatch, *, llm_provider="ollama"):
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(tmp_path / "memory"))

    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)

    audit = AuditService(SqlAlchemyAuditRepo(sm))
    store = FakeMemoryStore()
    record_repo = SqlAlchemyMemoryRecordRepo(sm)

    mem_service = MemoryService(
        resource_service=None,  # type: ignore[arg-type]
        store=store,
        records=record_repo,
        audit=audit,
        store_dir=memory_store_dir,
    )
    kind = make_memory_kind(mem_service)
    resource_svc = ResourceService(
        kinds={"memory": kind},
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
    )
    mem_service._resources = resource_svc  # type: ignore[attr-defined]

    cfg = (
        MemoryStoreConfig(
            llm_provider=llm_provider,  # type: ignore[arg-type]
            llm_model="llama3.1" if llm_provider == "ollama" else None,
        )
        if llm_provider != "none"
        else MemoryStoreConfig()
    )

    return resource_svc, mem_service, store, engine, cfg


@pytest.mark.acceptance(spec="007-memory", scenario="create a memory store")
async def test_create_store(tmp_path, monkeypatch):
    rs, _ms, _s, engine, cfg = await _services(tmp_path, monkeypatch)
    try:
        r = await rs.register(
            kind="memory", name="coding-prefs", config=cfg.model_dump(), actor="cli"
        )
        assert r.name == "coding-prefs"
    finally:
        await engine.dispose()


@pytest.mark.acceptance(spec="007-memory", scenario="agent adds a memory")
async def test_add_memory(tmp_path, monkeypatch):
    rs, ms, store, engine, cfg = await _services(tmp_path, monkeypatch)
    try:
        await rs.register(kind="memory", name="s1", config=cfg.model_dump(), actor="cli")
        m = await ms.add(store_name="s1", text="uses tabs", actor="agent")
        assert m.text == "uses tabs"
        assert store.add_calls == 1
    finally:
        await engine.dispose()


@pytest.mark.acceptance(spec="007-memory", scenario="agent searches memories")
async def test_search_memories(tmp_path, monkeypatch):
    rs, ms, _store, engine, cfg = await _services(tmp_path, monkeypatch)
    try:
        await rs.register(kind="memory", name="s1", config=cfg.model_dump(), actor="cli")
        await ms.add(store_name="s1", text="uses tabs", actor="agent")
        await ms.add(store_name="s1", text="prefers kebab-case branches", actor="agent")
        hits = await ms.search(store_name="s1", query="tabs", top_k=5)
        assert len(hits) >= 1
        assert "tabs" in hits[0].text
    finally:
        await engine.dispose()


@pytest.mark.acceptance(spec="007-memory", scenario="list memories in a store")
async def test_list_memories(tmp_path, monkeypatch):
    rs, ms, _store, engine, cfg = await _services(tmp_path, monkeypatch)
    try:
        await rs.register(kind="memory", name="s1", config=cfg.model_dump(), actor="cli")
        await ms.add(store_name="s1", text="a", actor="agent")
        await ms.add(store_name="s1", text="b", actor="user")
        rows, total = await ms.list_memories(store_name="s1", limit=10, offset=0)
        assert total == 2
        assert {r.text for r in rows} == {"a", "b"}
    finally:
        await engine.dispose()


@pytest.mark.acceptance(spec="007-memory", scenario="edit a memory")
async def test_update_memory(tmp_path, monkeypatch):
    rs, ms, _store, engine, cfg = await _services(tmp_path, monkeypatch)
    try:
        await rs.register(kind="memory", name="s1", config=cfg.model_dump(), actor="cli")
        m = await ms.add(store_name="s1", text="old", actor="user")
        updated = await ms.update(store_name="s1", memory_id=m.id, new_text="new", actor="user")
        assert updated.text == "new"
    finally:
        await engine.dispose()


@pytest.mark.acceptance(spec="007-memory", scenario="agent deletes a single memory")
async def test_delete_memory(tmp_path, monkeypatch):
    rs, ms, _store, engine, cfg = await _services(tmp_path, monkeypatch)
    try:
        await rs.register(kind="memory", name="s1", config=cfg.model_dump(), actor="cli")
        m = await ms.add(store_name="s1", text="x", actor="agent")
        await ms.delete(store_name="s1", memory_id=m.id, actor="agent")
        with pytest.raises(MemoryNotFound):
            await ms.get(store_name="s1", memory_id=m.id)
    finally:
        await engine.dispose()


@pytest.mark.acceptance(spec="007-memory", scenario="clear all memories in a store")
async def test_clear_memories(tmp_path, monkeypatch):
    rs, ms, _store, engine, cfg = await _services(tmp_path, monkeypatch)
    try:
        await rs.register(kind="memory", name="s1", config=cfg.model_dump(), actor="cli")
        await ms.add(store_name="s1", text="a", actor="agent")
        await ms.add(store_name="s1", text="b", actor="user")
        cleared = await ms.clear(store_name="s1", actor="user")
        assert cleared >= 2
        _rows, total = await ms.list_memories(store_name="s1", limit=10, offset=0)
        assert total == 0
    finally:
        await engine.dispose()


@pytest.mark.acceptance(
    spec="007-memory",
    scenario="delete a memory store cleans up everything",
)
async def test_cleanup_store(tmp_path, monkeypatch):
    """TEST26-008: route the test via ``resource_service.delete`` so the
    real on_delete hook runs (CODE26-001 made it await-able), then assert
    the per-store directory + records are gone.

    Previously this test called ``ms.cleanup_store`` directly which bypassed
    the kind hook — a regression in the hook (e.g. fire-and-forget vs awaited)
    would not be caught.
    """
    from coffer.domain.errors import ResourceNotFound
    from coffer.domain.resource import ResourceRef
    from coffer.infrastructure.memory.paths import memory_store_dir

    rs, ms, store, engine, cfg = await _services(tmp_path, monkeypatch)
    try:
        await rs.register(kind="memory", name="s1", config=cfg.model_dump(), actor="cli")
        await ms.add(store_name="s1", text="a", actor="agent")

        store_dir = memory_store_dir("s1")
        store_dir.mkdir(parents=True, exist_ok=True)
        (store_dir / "marker.txt").write_text("on-disk state")

        await rs.delete(ResourceRef("memory", "s1"), actor="cli")

        # on_delete ran to completion: store dropped, dir removed, resource
        # row gone, and a follow-up ``get`` raises ResourceNotFound.
        assert store.drop_calls == 1
        assert not store_dir.exists()
        with pytest.raises(ResourceNotFound):
            await rs.get(ResourceRef("memory", "s1"))
    finally:
        await engine.dispose()


@pytest.mark.acceptance(spec="007-memory", scenario="memories persist across daemon restarts")
async def test_memories_persist_across_restart(tmp_path, monkeypatch):
    """Simulate a daemon restart: dispose the engine, re-create services on
    the same DB file, and verify the memory rows are still present.

    Covers the SQL-side persistence (``memory_records`` rows). mem0's own
    on-disk vector-store persistence is a property of the mem0 library and
    is not unit-tested here — adding a real vector-store round-trip would
    require a real LLM + embedding model + chroma backend, which is out of
    scope for this PR (TEST26-009).
    """
    rs, ms, _store, engine, cfg = await _services(tmp_path, monkeypatch)
    try:
        await rs.register(kind="memory", name="persist1", config=cfg.model_dump(), actor="cli")
        await ms.add(store_name="persist1", text="durable fact", actor="user")
        await ms.add(store_name="persist1", text="another fact", actor="agent")
    finally:
        await engine.dispose()

    # "Restart" — rebuild everything against the same DB file.
    _rs2, ms2, _s2, engine2, _cfg2 = await _services(tmp_path, monkeypatch)
    try:
        rows, total = await ms2.list_memories(store_name="persist1", limit=10, offset=0)
        assert total == 2
        texts = sorted(r.text for r in rows)
        assert texts == ["another fact", "durable fact"]
    finally:
        await engine2.dispose()


async def test_add_with_provider_none_rejects(tmp_path, monkeypatch):
    rs, ms, _store, engine, cfg = await _services(tmp_path, monkeypatch, llm_provider="none")
    try:
        await rs.register(
            kind="memory",
            name="s-no-llm",
            config=cfg.model_dump(),
            actor="cli",
        )
        with pytest.raises(LLMNotConfigured):
            await ms.add(store_name="s-no-llm", text="hello", actor="agent")
    finally:
        await engine.dispose()


async def test_add_text_too_long_rejected(tmp_path, monkeypatch):
    rs, ms, _store, engine, cfg = await _services(tmp_path, monkeypatch)
    try:
        await rs.register(kind="memory", name="s1", config=cfg.model_dump(), actor="cli")
        too_long = "x" * (cfg.max_memory_chars + 1)
        with pytest.raises(MemoryRejected) as exc:
            await ms.add(store_name="s1", text=too_long, actor="user")
        assert exc.value.reason == "too_long"
    finally:
        await engine.dispose()
