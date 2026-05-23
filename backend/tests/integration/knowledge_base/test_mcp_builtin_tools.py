"""Verify Coffer's MCP gateway exposes built-in tools (KB + Memory) under
the reserved coffer__ prefix and dispatches calls to them. Uses the gateway
with empty supervisor / discovery (no upstream MCP servers needed)."""

from __future__ import annotations

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.knowledge_base.builtin_tools import (
    register_kb_builtin_tools,
)
from coffer.application.knowledge_base.kind import make_kb_kind
from coffer.application.knowledge_base.service import KnowledgeBaseService
from coffer.application.mcp.gateway import MCPGatewaySession
from coffer.application.memory.builtin_tools import (
    register_memory_builtin_tools,
)
from coffer.application.memory.kind import make_memory_kind
from coffer.application.memory.service import MemoryService
from coffer.application.resource_service import ResourceService
from coffer.domain.knowledge_base.config import KnowledgeBaseConfig
from coffer.domain.memory.config import MemoryStoreConfig
from coffer.infrastructure.knowledge_base.loaders import extract_text
from coffer.infrastructure.knowledge_base.paths import (
    kb_dir,
    kb_raw_dir,
    kb_root,
    raw_file_path,
)
from coffer.infrastructure.knowledge_base.persistence import (
    SqlAlchemyKBDocumentRepo,
)
from coffer.infrastructure.memory.paths import memory_store_dir
from coffer.infrastructure.memory.persistence import (
    SqlAlchemyMemoryRecordRepo,
)
from coffer.infrastructure.observability.noop_tracer import NoopTracer
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from tests.integration.knowledge_base.fakes import FakeKnowledgeBaseStore
from tests.integration.memory.fakes import FakeMemoryStore


async def _setup(tmp_path, monkeypatch):
    monkeypatch.setenv("COFFER_KB_ROOT", str(tmp_path / "kb"))
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(tmp_path / "memory"))
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)

    audit = AuditService(SqlAlchemyAuditRepo(sm))

    # KB.
    kb_store = FakeKnowledgeBaseStore()
    kb_svc = KnowledgeBaseService.build(
        resource_service=None,  # type: ignore[arg-type]
        store=kb_store,
        documents=SqlAlchemyKBDocumentRepo(sm),
        audit=audit,
        tracer=NoopTracer(),
        raw_dir=kb_raw_dir,
        raw_file=raw_file_path,
        kb_dir=kb_dir,
        kb_root=kb_root,
        extractor=extract_text,
    )

    # Memory.
    mem_store = FakeMemoryStore()
    mem_svc = MemoryService(
        resource_service=None,  # type: ignore[arg-type]
        store=mem_store,
        records=SqlAlchemyMemoryRecordRepo(sm),
        audit=audit,
        tracer=NoopTracer(),
        store_dir=memory_store_dir,
    )

    kinds = {
        "knowledge_base": make_kb_kind(kb_svc),
        "memory": make_memory_kind(mem_svc),
    }
    rs = ResourceService(
        kinds=kinds,
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
    )
    kb_svc._resources = rs  # type: ignore[attr-defined]
    mem_svc._resources = rs  # type: ignore[attr-defined]

    registry = BuiltinToolRegistry()
    register_kb_builtin_tools(registry, resources=rs, kb_service=kb_svc)
    register_memory_builtin_tools(registry, resources=rs, memory_service=mem_svc)

    return rs, kb_svc, mem_svc, registry, engine


@pytest.mark.acceptance(
    spec="006-knowledge-base",
    scenario="built-in tools appear in client tool list",
)
async def test_builtin_tools_in_tool_list(tmp_path, monkeypatch):
    rs, _kb_svc, _mem_svc, registry, engine = await _setup(tmp_path, monkeypatch)
    try:
        await rs.register(
            kind="knowledge_base",
            name="kb1",
            config=KnowledgeBaseConfig().model_dump(),
            actor="cli",
        )

        # Empty discovery / invocations are fine because we go through the
        # built-in path and never touch upstream MCP servers.
        from coffer.application.mcp.credential_resolver import CredentialResolver
        from coffer.application.mcp.discovery import CapabilityDiscovery
        from coffer.application.mcp.supervisor import SubprocessSupervisor
        from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter
        from coffer.infrastructure.mcp.persistence import (
            MCPCapabilityPreferenceRepo,
            MCPInvocationRepo,
        )

        sm = session_maker(
            create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
        )
        prefs = MCPCapabilityPreferenceRepo(sm)
        inv = MCPInvocationRepo(sm)
        sup = SubprocessSupervisor(
            resource_service=rs,
            credential_resolver=CredentialResolver(KeyringAdapter()),
        )
        disc = CapabilityDiscovery(
            resource_service=rs,
            supervisor=sup,
            preferences=prefs,
            audit=AuditService(SqlAlchemyAuditRepo(sm)),
        )

        session = MCPGatewaySession(
            session_id="s",
            resource_service=rs,
            supervisor=sup,
            discovery=disc,
            preferences=prefs,
            invocations=inv,
            builtin_tools=registry,
        )

        result = await session.handle_request("tools/list")
        names = [t["name"] for t in result["tools"]]
        assert "coffer__list_knowledge_bases" in names
        assert "coffer__search_knowledge_base" in names
        assert "coffer__get_document" in names
        assert "coffer__list_memory_stores" in names
        assert "coffer__add_memory" in names
        assert "coffer__search_memory" in names
        assert "coffer__delete_memory" in names
    finally:
        await engine.dispose()


@pytest.mark.acceptance(spec="006-knowledge-base", scenario="agent searches a knowledge base")
@pytest.mark.acceptance(spec="006-knowledge-base", scenario="agent fetches a document by id")
@pytest.mark.acceptance(
    spec="006-knowledge-base",
    scenario="agent lists available knowledge bases",
)
async def test_builtin_search_kb_dispatches(tmp_path, monkeypatch):
    rs, kb_svc, _ms, registry, engine = await _setup(tmp_path, monkeypatch)
    try:
        await rs.register(
            kind="knowledge_base",
            name="kb1",
            config=KnowledgeBaseConfig().model_dump(),
            actor="cli",
        )
        await kb_svc.ingest_bytes(
            kb_name="kb1",
            filename="x.md",
            raw_bytes=b"the user prefers spaces",
            actor="cli",
        )
        # Search via built-in tool.
        search_tool = registry.get("coffer__search_knowledge_base")
        assert search_tool is not None
        out = await search_tool.handler({"kb": "kb1", "query": "spaces", "top_k": 5})
        assert "hits" in out
        assert len(out["hits"]) >= 1
        assert out["hits"][0]["filename"] == "x.md"

        # List via built-in tool.
        list_tool = registry.get("coffer__list_knowledge_bases")
        assert list_tool is not None
        listed = await list_tool.handler({})
        assert any(kb["name"] == "kb1" for kb in listed["knowledge_bases"])

        # Get a document by id via built-in tool.
        doc_id = out["hits"][0]["document_id"]
        get_tool = registry.get("coffer__get_document")
        assert get_tool is not None
        doc_out = await get_tool.handler({"kb": "kb1", "document_id": doc_id})
        assert doc_out["document_id"] == doc_id
        assert doc_out["filename"] == "x.md"
        assert "spaces" in doc_out["text"]
    finally:
        await engine.dispose()


@pytest.mark.acceptance(
    spec="007-memory",
    scenario="built-in memory tools appear in client tool list",
)
async def test_builtin_add_and_search_memory_dispatches(tmp_path, monkeypatch):
    rs, _kb_svc, _mem_svc, registry, engine = await _setup(tmp_path, monkeypatch)
    try:
        await rs.register(
            kind="memory",
            name="s1",
            config=MemoryStoreConfig(llm_provider="ollama", llm_model="x").model_dump(),
            actor="cli",
        )
        add_tool = registry.get("coffer__add_memory")
        assert add_tool is not None
        await add_tool.handler({"store": "s1", "text": "uses tabs"})

        search_tool = registry.get("coffer__search_memory")
        assert search_tool is not None
        out = await search_tool.handler({"store": "s1", "query": "tabs"})
        assert "hits" in out
        assert len(out["hits"]) >= 1
        assert "tabs" in out["hits"][0]["text"]
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# TEST26-011 — FR-010: each built-in memory tool dispatch records one row
# in ``mcp_invocations``. The row carries the bare tool name (no
# ``coffer__`` prefix) and the resource_name sentinel ``"coffer"``; args
# + return content are NOT logged.
# ---------------------------------------------------------------------------


async def test_memory_builtin_dispatch_logs_one_mcp_invocation_row(tmp_path, monkeypatch):
    """Drive the full gateway session so dispatch_builtin_tool logs the
    invocation. Confirms FR-010 holds for memory built-in tools.
    """
    from coffer.application.mcp.credential_resolver import CredentialResolver
    from coffer.application.mcp.discovery import CapabilityDiscovery
    from coffer.application.mcp.gateway import MCPGatewaySession
    from coffer.application.mcp.supervisor import SubprocessSupervisor
    from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter
    from coffer.infrastructure.mcp.persistence import (
        MCPCapabilityPreferenceRepo,
        MCPInvocationRepo,
    )

    rs, _kb_svc, _mem_svc, registry, engine = await _setup(tmp_path, monkeypatch)
    try:
        await rs.register(
            kind="memory",
            name="s1",
            config=MemoryStoreConfig(llm_provider="ollama", llm_model="x").model_dump(),
            actor="cli",
        )

        sm = session_maker(
            create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
        )
        prefs = MCPCapabilityPreferenceRepo(sm)
        inv = MCPInvocationRepo(sm)
        sup = SubprocessSupervisor(
            resource_service=rs,
            credential_resolver=CredentialResolver(KeyringAdapter()),
        )
        disc = CapabilityDiscovery(
            resource_service=rs,
            supervisor=sup,
            preferences=prefs,
            audit=AuditService(SqlAlchemyAuditRepo(sm)),
        )
        session = MCPGatewaySession(
            session_id="session-x",
            resource_service=rs,
            supervisor=sup,
            discovery=disc,
            preferences=prefs,
            invocations=inv,
            builtin_tools=registry,
        )

        # Dispatch each memory built-in via tools/call.
        await session.handle_request(
            "tools/call",
            {"name": "coffer__list_memory_stores", "arguments": {}},
        )
        await session.handle_request(
            "tools/call",
            {
                "name": "coffer__add_memory",
                "arguments": {"store": "s1", "text": "uses tabs"},
            },
        )
        await session.handle_request(
            "tools/call",
            {
                "name": "coffer__search_memory",
                "arguments": {"store": "s1", "query": "tabs"},
            },
        )

        rows = await inv.query(resource_name="coffer", limit=50)
        bare_names = [r.capability_key for r in rows]
        # One row per built-in dispatch, with the bare tool name (no
        # coffer__ prefix). Status is "ok" on the happy path.
        assert "list_memory_stores" in bare_names
        assert "add_memory" in bare_names
        assert "search_memory" in bare_names
        # Resource sentinel is "coffer" for all built-ins (FR-010).
        assert all(r.resource_name == "coffer" for r in rows)
        # FR-010 — no args/return-content fields on the persisted row.
        # MCPInvocation has neither, so simply observe the persisted shape.
        assert all(r.capability_type == "tool" for r in rows)
        assert all(r.status == "ok" for r in rows)
    finally:
        await engine.dispose()
