"""Integration tests for the KB built-in MCP tools (TEST22-014, TEST22-009).

Exercises ``register_kb_builtin_tools`` end-to-end: registers the three
``coffer__*`` tools into a real ``BuiltinToolRegistry`` and invokes each
handler with dict args, asserting on the response shape returned to the
gateway. This is the surface an agent actually sees through MCP.

The cross-cutting "agent lists available knowledge bases" acceptance
scenario lives on ``test_list_knowledge_bases_handler`` (TEST22-009 — was
previously parked on an HTTP-only test).
"""

from __future__ import annotations

import pytest

from coffer.application.builtin_tools import COFFER_TOOL_PREFIX, BuiltinToolRegistry
from coffer.application.knowledge_base.builtin_tools import register_kb_builtin_tools
from coffer.domain.knowledge_base.config import KnowledgeBaseConfig


async def _register_kb_and_ingest(bundle, *, kb_name: str = "kb1") -> str:
    """Create a KB + ingest a single document; return the document_id."""
    await bundle.resources.register(
        kind="knowledge_base",
        name=kb_name,
        config=KnowledgeBaseConfig().model_dump(),
        actor="cli",
        description="docs",
    )
    doc = await bundle.kb.ingest_bytes(
        kb_name=kb_name,
        filename="prefs.md",
        raw_bytes=b"the user prefers tabs over spaces",
        actor="cli",
    )
    return doc.id


def _registry_with_kb_tools(bundle) -> BuiltinToolRegistry:
    registry = BuiltinToolRegistry()
    register_kb_builtin_tools(
        registry,
        resources=bundle.resources,
        kb_service=bundle.kb,
    )
    return registry


def test_register_kb_builtin_tools_registers_three_tools(kb_bundle):
    registry = _registry_with_kb_tools(kb_bundle)
    names = {t.name for t in registry.list()}
    assert names == {"list_knowledge_bases", "search_knowledge_base", "get_document"}
    # The gateway exposes them under the coffer__ prefix.
    for bare in names:
        prefixed = f"{COFFER_TOOL_PREFIX}{bare}"
        assert registry.is_builtin(prefixed)
        assert registry.get(prefixed) is not None


@pytest.mark.acceptance(
    spec="006-knowledge-base",
    scenario="agent lists available knowledge bases",
)
async def test_list_knowledge_bases_handler(kb_bundle):
    """TEST22-009: the acceptance scenario is satisfied via the MCP tool,
    not the HTTP route — agents see KBs through the registered handler."""
    await _register_kb_and_ingest(kb_bundle, kb_name="designs")

    registry = _registry_with_kb_tools(kb_bundle)
    handler = registry.get(f"{COFFER_TOOL_PREFIX}list_knowledge_bases")
    assert handler is not None

    out = await handler.handler({})
    assert "knowledge_bases" in out, out
    listed = out["knowledge_bases"]
    assert isinstance(listed, list)
    assert any(kb["name"] == "designs" for kb in listed)
    one = next(kb for kb in listed if kb["name"] == "designs")
    assert one["document_count"] == 1
    assert one["embedding_model"]  # default model from KnowledgeBaseConfig
    assert one["description"] == "docs"


async def test_search_knowledge_base_handler_returns_ranked_hits(kb_bundle):
    """TEST22-014: search handler returns the ranked-hits envelope."""
    await _register_kb_and_ingest(kb_bundle, kb_name="kb1")

    registry = _registry_with_kb_tools(kb_bundle)
    handler = registry.get(f"{COFFER_TOOL_PREFIX}search_knowledge_base")
    assert handler is not None

    out = await handler.handler({"kb": "kb1", "query": "tabs", "top_k": 3})
    assert "hits" in out, out
    hits = out["hits"]
    assert isinstance(hits, list)
    assert len(hits) >= 1
    hit = hits[0]
    # Required hit keys from the spec contract.
    assert set(hit.keys()) >= {"text", "document_id", "filename", "score", "position"}
    assert hit["filename"] == "prefs.md"
    assert hit["score"] > 0
    assert isinstance(hit["position"], int)


async def test_search_knowledge_base_handler_defaults_top_k(kb_bundle):
    await _register_kb_and_ingest(kb_bundle, kb_name="kb1")
    registry = _registry_with_kb_tools(kb_bundle)
    handler = registry.get(f"{COFFER_TOOL_PREFIX}search_knowledge_base")
    assert handler is not None
    # No top_k → handler must fall back to its default (5) without erroring.
    out = await handler.handler({"kb": "kb1", "query": "tabs"})
    assert "hits" in out


async def test_get_document_handler_returns_text_and_metadata(kb_bundle):
    """TEST22-014: get_document handler returns the document body."""
    doc_id = await _register_kb_and_ingest(kb_bundle, kb_name="kb1")

    registry = _registry_with_kb_tools(kb_bundle)
    handler = registry.get(f"{COFFER_TOOL_PREFIX}get_document")
    assert handler is not None

    out = await handler.handler({"kb": "kb1", "document_id": doc_id})
    # The actual response envelope from builtin_tools.py.
    assert out["filename"] == "prefs.md"
    assert out["document_id"] == doc_id
    assert "the user prefers tabs over spaces" in out["text"]
    assert out["size_bytes"] > 0
