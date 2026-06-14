# backend/tests/unit/application/mcp/test_gateway_tool_search.py
import pytest

from coffer.application.mcp import gateway_tool_search
from coffer.application.mcp.gateway_tool_search import (
    TOOL_SEARCH_NAME,
    execute_tool_search,
    tool_search_descriptor,
)


def _agg():
    return [
        {
            "name": "github__create_issue",
            "description": "Create a GitHub issue",
            "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}}},
        },
        {
            "name": "slack__post_message",
            "description": "Post a Slack message",
            "inputSchema": {"type": "object"},
        },
        {"name": "coffer__recall", "description": "Recall memory", "inputSchema": {}},
    ]


class _KeywordEmbedder:
    """Deterministic 2-d embedder: axis 0 = 'issue', axis 1 = 'message'."""

    def __init__(self) -> None:
        self.embed_calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.embed_calls.append(list(texts))
        return [[float("issue" in t.lower()), float("message" in t.lower())] for t in texts]


class _BrokenEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding engine unavailable")


def test_descriptor_shape():
    d = tool_search_descriptor()
    assert d["name"] == TOOL_SEARCH_NAME == "coffer__search_tools"
    assert d["inputSchema"]["required"] == ["query"]


async def test_execute_returns_ranked_real_schema():
    out = await execute_tool_search({"query": "create github issue"}, _agg())
    assert out["tools"][0]["name"] == "github__create_issue"
    assert "inputSchema" in out["tools"][0]
    assert out["tools"][0]["score"] > 0


async def test_execute_excludes_coffer_builtins():
    out = await execute_tool_search({"query": "recall memory"}, _agg())
    assert all(not t["name"].startswith("coffer__") for t in out["tools"])
    assert out["total_searched"] == 2  # coffer__recall excluded


async def test_execute_clamps_top_k():
    out = await execute_tool_search({"query": "post message", "top_k": 999}, _agg())
    assert len(out["tools"]) <= 2


async def test_execute_rejects_empty_query():
    with pytest.raises(ValueError):
        await execute_tool_search({"query": "  "}, _agg())
    with pytest.raises(ValueError):
        await execute_tool_search({}, _agg())


async def test_execute_semantic_ranks_by_embedding_similarity():
    embedder = _KeywordEmbedder()
    out = await execute_tool_search({"query": "send a message"}, _agg(), embedder)
    # 'message' query embeds to axis 1, matching the Slack tool over GitHub.
    assert out["tools"][0]["name"] == "slack__post_message"
    assert out["total_searched"] == 2
    assert embedder.embed_calls  # the embedder was actually used


async def test_execute_falls_back_to_bm25_when_embedder_fails():
    # A broken embedder must not hard-fail the search — it degrades to BM25.
    out = await execute_tool_search({"query": "create github issue"}, _agg(), _BrokenEmbedder())
    assert out["tools"][0]["name"] == "github__create_issue"


async def test_execute_caches_tool_embeddings_across_calls():
    gateway_tool_search._EMBED_CACHE.clear()
    embedder = _KeywordEmbedder()
    await execute_tool_search({"query": "issue"}, _agg(), embedder)
    await execute_tool_search({"query": "message"}, _agg(), embedder)
    # The tool (doc) texts are embedded once and cached; across both calls only a
    # single multi-text batch (the docs) is issued — later calls embed only the
    # query.
    doc_batches = [call for call in embedder.embed_calls if len(call) > 1]
    assert len(doc_batches) == 1
