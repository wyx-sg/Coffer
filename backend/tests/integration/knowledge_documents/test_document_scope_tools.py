"""Integration: the eight built-in MCP tools, driven against a NAMED collection.

The sibling ``knowledge_scope/test_entry_scope_tools.py`` drives the same eight
against the two auto-scopes. Here the material is ingested documents, which is
what the pre-merge ``knowledge_base`` tools existed for — the point of these
tests is that the merged tools still do everything those seven did, without the
caller having to say which kind of thing it is after.
"""

from __future__ import annotations

import pytest

from coffer.application.builtin_tools import COFFER_TOOL_PREFIX, BuiltinToolRegistry
from coffer.application.knowledge.builtin_tools import register_knowledge_builtin_tools
from coffer.application.knowledge.document_tools import register_document_builtin_tools
from coffer.domain.knowledge.document import KIND_KNOWLEDGE

pytestmark = pytest.mark.asyncio


async def _registry(kb) -> BuiltinToolRegistry:
    reg = BuiltinToolRegistry()
    register_knowledge_builtin_tools(
        reg,
        knowledge_service=kb.service,
        handoff_service=None,  # type: ignore[arg-type]
    )
    register_document_builtin_tools(reg, resources=kb.resources, knowledge_service=kb.service)
    return reg


def _tool(reg: BuiltinToolRegistry, name: str):
    tool = reg.get(f"{COFFER_TOOL_PREFIX}{name}")
    assert tool is not None, f"{name} not registered"
    return tool


@pytest.mark.acceptance(spec="007-memory", scenario="built-in KB tools appear in client tool list")
async def test_the_eight_tools_are_registered(kb) -> None:
    reg = await _registry(kb)
    # Twelve tools over two kinds became eight over one. Documents stay
    # co-managed (spec 007 FR-062): read AND write are both here.
    assert {t.name for t in reg.list()} == {
        "search",
        "grep",
        "read",
        "list",
        "write",
        "delete",
        "set_handoff",
        "resume",
    }
    # The gateway prefixes on list.
    assert reg.is_builtin(f"{COFFER_TOOL_PREFIX}search")
    assert reg.is_builtin(f"{COFFER_TOOL_PREFIX}write")


@pytest.mark.acceptance(spec="007-memory", scenario="agent searches a knowledge base")
async def test_search_finds_an_ingested_document(kb) -> None:
    await kb.create_kb("kb1")
    await kb.service.ingest_bytes(
        scope_name="kb1", filename="a.md", raw_bytes=b"# Fox\n\nbrown fox jumps", actor="user"
    )
    reg = await _registry(kb)
    out = await _tool(reg, "search").handler({"scope": "kb1", "query": "fox"})
    assert out["scope"] == "kb1"
    assert len(out["hits"]) == 1
    assert "fox" in out["hits"][0]["text"]
    # The hit's id is what coffer__read takes.
    assert out["hits"][0]["id"]


@pytest.mark.acceptance(spec="007-memory", scenario="agent greps a knowledge base")
async def test_grep_matches_a_literal_line(kb) -> None:
    await kb.create_kb("kb1")
    await kb.service.ingest_bytes(
        scope_name="kb1", filename="a.md", raw_bytes=b"# T\n\nthe make release line", actor="user"
    )
    reg = await _registry(kb)
    out = await _tool(reg, "grep").handler({"scope": "kb1", "pattern": "make release"})
    assert len(out["hits"]) >= 1
    assert "make release" in out["hits"][0]["line"]


@pytest.mark.acceptance(spec="007-memory", scenario="agent reads a document")
async def test_read_returns_the_full_markdown(kb) -> None:
    await kb.create_kb("kb1")
    doc = await kb.service.ingest_bytes(
        scope_name="kb1", filename="a.md", raw_bytes=b"# Title\n\nbody text", actor="user"
    )
    reg = await _registry(kb)
    out = await _tool(reg, "read").handler({"scope": "kb1", "id": doc.id})
    assert out["id"] == doc.id
    assert out["type"] == "document"
    assert "body text" in out["text"]
    assert out["source_mode"] == "converted"


async def test_list_shows_the_scope_catalogue_and_one_scope(kb) -> None:
    await kb.create_kb("kb1")
    await kb.service.ingest_bytes(
        scope_name="kb1", filename="a.md", raw_bytes=b"# A\n\nx", actor="user"
    )
    reg = await _registry(kb)
    listing = _tool(reg, "list")

    catalogue = await listing.handler({"all": True})
    assert [s["scope"] for s in catalogue["scopes"]] == ["kb1"]
    assert catalogue["scopes"][0]["document_count"] == 1

    one = await listing.handler({"scope": "kb1"})
    assert one["document_total"] == 1
    assert one["entry_total"] == 0
    assert one["documents"][0]["title"]


@pytest.mark.acceptance(spec="007-memory", scenario="agent adds a document via MCP")
async def test_write_with_a_filename_adds_a_document(kb) -> None:
    await kb.create_kb("kb1")
    reg = await _registry(kb)
    out = await _tool(reg, "write").handler(
        {"scope": "kb1", "filename": "agent-note.md", "text": "# Note\n\nwombat facts"}
    )
    assert out["type"] == "document"
    assert out["id"] and out["source_mode"] == "converted"
    # The added document is searchable.
    assert len((await kb.service.search(scope_name="kb1", query="wombat", top_k=5)).passages) == 1


@pytest.mark.acceptance(spec="007-memory", scenario="agent edits a document via MCP")
async def test_write_with_an_id_rewrites_a_document(kb) -> None:
    await kb.create_kb("kb1")
    doc = await kb.service.ingest_bytes(
        scope_name="kb1", filename="a.md", raw_bytes=b"# A\n\noriginal otter body", actor="user"
    )
    reg = await _registry(kb)
    out = await _tool(reg, "write").handler(
        {"scope": "kb1", "id": doc.id, "text": "# A\n\nedited seal body"}
    )
    assert out["id"] == doc.id and out["source_mode"] == "edited"
    assert (await kb.service.search(scope_name="kb1", query="otter", top_k=5)).passages == ()
    assert len((await kb.service.search(scope_name="kb1", query="seal", top_k=5)).passages) == 1


@pytest.mark.acceptance(spec="007-memory", scenario="agent deletes a document via MCP")
async def test_delete_removes_a_document(kb) -> None:
    await kb.create_kb("kb1")
    doc = await kb.service.ingest_bytes(
        scope_name="kb1", filename="a.md", raw_bytes=b"# A\n\nephemeral body", actor="user"
    )
    reg = await _registry(kb)
    out = await _tool(reg, "delete").handler({"scope": "kb1", "id": doc.id})
    assert out["deleted"] is True and out["id"] == doc.id and out["type"] == "document"
    assert await kb.documents.count_documents(KIND_KNOWLEDGE, "kb1") == 0
    # The MCP delete is audited with the agent as actor (FR-018).
    events = await kb.audit.query(kind=KIND_KNOWLEDGE, name="kb1", limit=50)
    deleted = [e for e in events if e.event_type == "kb_document_deleted"]
    assert deleted and deleted[0].actor == "agent"


async def test_write_without_a_filename_files_an_entry_in_the_same_scope(kb) -> None:
    """The merge's whole point: one scope holds both, and the caller picks by
    what it passes rather than by which tool it reaches for."""
    await kb.create_kb("kb1")
    reg = await _registry(kb)
    entry = await _tool(reg, "write").handler(
        {"scope": "kb1", "text": "the daemon restarts on port drift", "title": "port drift"}
    )
    assert entry["type"] == "entry" and entry["status"] == "created"

    listed = await _tool(reg, "list").handler({"scope": "kb1"})
    assert listed["entry_total"] == 1

    # …and coffer__read resolves an entry id without being told which lane.
    read = await _tool(reg, "read").handler({"scope": "kb1", "id": entry["id"]})
    assert read["type"] == "entry"
    assert "port drift" in read["text"] or "port drift" in read["title"]


async def test_delete_falls_back_to_the_entry_lane(kb) -> None:
    await kb.create_kb("kb1")
    reg = await _registry(kb)
    entry = await _tool(reg, "write").handler({"scope": "kb1", "text": "transient", "title": "t"})
    out = await _tool(reg, "delete").handler({"scope": "kb1", "id": entry["id"]})
    assert out["deleted"] is True and out["type"] == "entry"
    assert (await _tool(reg, "list").handler({"scope": "kb1"}))["entry_total"] == 0
