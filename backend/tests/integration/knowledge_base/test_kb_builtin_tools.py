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
    assert names == {
        "list_knowledge_bases",
        "search_knowledge",
        "grep_knowledge",
        "read_document",
    }
    # gateway prefixes on list; no write tool exists.
    assert reg.is_builtin(f"{COFFER_TOOL_PREFIX}search_knowledge")
    assert not any("ingest" in n or "delete" in n or "write" in n for n in names)


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
    assert out["mode"] == "keyword"
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
