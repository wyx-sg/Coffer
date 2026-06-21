"""Integration: the read-only KB built-in MCP tools."""

from __future__ import annotations

import pytest

from coffer.application.builtin_tools import COFFER_TOOL_PREFIX, BuiltinToolRegistry
from coffer.application.knowledge_base.builtin_tools import register_kb_builtin_tools

pytestmark = pytest.mark.asyncio


async def _registry(kb) -> BuiltinToolRegistry:
    reg = BuiltinToolRegistry()
    register_kb_builtin_tools(reg, resources=kb.resources, kb_service=kb.service)
    return reg


@pytest.mark.acceptance(
    spec="006-knowledge-base", scenario="built-in KB tools appear in client tool list"
)
async def test_kb_tools_registered(kb) -> None:
    reg = await _registry(kb)
    names = {t.name for t in reg.list()}
    # Documents are co-managed (ADR-028): read AND write tools are present.
    assert names == {
        "list_knowledge_bases",
        "search_knowledge",
        "grep_knowledge",
        "read_document",
        "add_document",
        "edit_document",
        "delete_document",
    }
    # gateway prefixes on list.
    assert reg.is_builtin(f"{COFFER_TOOL_PREFIX}search_knowledge")
    assert reg.is_builtin(f"{COFFER_TOOL_PREFIX}add_document")


@pytest.mark.acceptance(spec="006-knowledge-base", scenario="agent searches a knowledge base")
async def test_search_tool_returns_passages(kb) -> None:
    await kb.create_kb("kb1")
    await kb.service.ingest_bytes(
        kb_name="kb1", filename="a.md", raw_bytes=b"# Fox\n\nbrown fox jumps", actor="user"
    )
    reg = await _registry(kb)
    tool = reg.get(f"{COFFER_TOOL_PREFIX}search_knowledge")
    assert tool is not None
    out = await tool.handler({"kb": "kb1", "query": "fox"})
    # One query → one answer: the MCP tool no longer surfaces mode / fallback.
    assert "mode" not in out
    assert "fallback" not in out
    assert len(out["passages"]) == 1
    assert out["passages"][0]["document_id"]


@pytest.mark.acceptance(spec="006-knowledge-base", scenario="agent greps a knowledge base")
async def test_grep_tool(kb) -> None:
    await kb.create_kb("kb1")
    await kb.service.ingest_bytes(
        kb_name="kb1", filename="a.md", raw_bytes=b"# T\n\nthe make release line", actor="user"
    )
    reg = await _registry(kb)
    tool = reg.get(f"{COFFER_TOOL_PREFIX}grep_knowledge")
    assert tool is not None
    out = await tool.handler({"kb": "kb1", "pattern": "make release"})
    assert len(out["hits"]) >= 1
    assert "make release" in out["hits"][0]["line"]


@pytest.mark.acceptance(spec="006-knowledge-base", scenario="agent reads a document")
async def test_read_document_tool(kb) -> None:
    await kb.create_kb("kb1")
    doc = await kb.service.ingest_bytes(
        kb_name="kb1", filename="a.md", raw_bytes=b"# Title\n\nbody text", actor="user"
    )
    reg = await _registry(kb)
    tool = reg.get(f"{COFFER_TOOL_PREFIX}read_document")
    assert tool is not None
    out = await tool.handler({"kb": "kb1", "document_id": doc.id})
    assert out["document_id"] == doc.id
    assert "body text" in out["markdown"]
    assert out["source_mode"] == "converted"


async def test_list_tool(kb) -> None:
    await kb.create_kb("kb1")
    await kb.service.ingest_bytes(
        kb_name="kb1", filename="a.md", raw_bytes=b"# A\n\nx", actor="user"
    )
    reg = await _registry(kb)
    tool = reg.get(f"{COFFER_TOOL_PREFIX}list_knowledge_bases")
    assert tool is not None
    out = await tool.handler({})
    assert len(out["knowledge_bases"]) == 1
    assert out["knowledge_bases"][0]["name"] == "kb1"
    assert out["knowledge_bases"][0]["document_count"] == 1


@pytest.mark.acceptance(spec="006-knowledge-base", scenario="agent adds a document via MCP")
async def test_add_document_tool(kb) -> None:
    await kb.create_kb("kb1")
    reg = await _registry(kb)
    tool = reg.get(f"{COFFER_TOOL_PREFIX}add_document")
    assert tool is not None
    out = await tool.handler(
        {"kb": "kb1", "filename": "agent-note.md", "content": "# Note\n\nwombat facts"}
    )
    assert out["document_id"] and out["source_mode"] == "converted"
    # The added document is searchable, and an INGEST was audited with the agent actor.
    assert len((await kb.service.search(kb_name="kb1", query="wombat", top_k=5)).passages) == 1
    events = await kb.audit.query(kind="knowledge_base", name="kb1", limit=50)
    ingested = [e for e in events if e.event_type == "kb_document_ingested"]
    assert ingested and ingested[0].actor == "agent"


@pytest.mark.acceptance(spec="006-knowledge-base", scenario="agent edits a document via MCP")
async def test_edit_document_tool(kb) -> None:
    await kb.create_kb("kb1")
    doc = await kb.service.ingest_bytes(
        kb_name="kb1", filename="a.md", raw_bytes=b"# A\n\noriginal otter body", actor="user"
    )
    reg = await _registry(kb)
    tool = reg.get(f"{COFFER_TOOL_PREFIX}edit_document")
    out = await tool.handler(
        {"kb": "kb1", "document_id": doc.id, "content": "# A\n\nedited seal body"}
    )
    assert out["document_id"] == doc.id and out["source_mode"] == "edited"
    assert (await kb.service.search(kb_name="kb1", query="otter", top_k=5)).passages == ()
    assert len((await kb.service.search(kb_name="kb1", query="seal", top_k=5)).passages) == 1
    # The MCP write is audited with the agent as actor (FR-018).
    events = await kb.audit.query(kind="knowledge_base", name="kb1", limit=50)
    updated = [e for e in events if e.event_type == "kb_document_updated"]
    assert updated and updated[0].actor == "agent"


@pytest.mark.acceptance(spec="006-knowledge-base", scenario="agent deletes a document via MCP")
async def test_delete_document_tool(kb) -> None:
    await kb.create_kb("kb1")
    doc = await kb.service.ingest_bytes(
        kb_name="kb1", filename="a.md", raw_bytes=b"# A\n\nephemeral body", actor="user"
    )
    reg = await _registry(kb)
    tool = reg.get(f"{COFFER_TOOL_PREFIX}delete_document")
    out = await tool.handler({"kb": "kb1", "document_id": doc.id})
    assert out["deleted"] is True and out["document_id"] == doc.id
    assert await kb.documents.count_documents("knowledge_base", "kb1") == 0
    # The MCP delete is audited with the agent as actor (FR-018).
    events = await kb.audit.query(kind="knowledge_base", name="kb1", limit=50)
    deleted = [e for e in events if e.event_type == "kb_document_deleted"]
    assert deleted and deleted[0].actor == "agent"
