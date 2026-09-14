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


async def test_execute_ranks_by_intent_words():
    """The one ranker left is BM25 over the tool name + description. The
    alternative cosine-over-embeddings path went with every other use of
    embeddings in Coffer."""
    out = await execute_tool_search({"query": "post slack message"}, _agg())
    assert out["tools"][0]["name"] == "slack__post_message"


def test_corpus_drops_the_duplicated_server_token():
    """`jira__jira_get_issue` tokenizes as jira, jira, get, issue — the server
    name lands twice at the ranker's name weight and crowds out the tokens that
    carry the intent."""
    corpus = gateway_tool_search._search_corpus(
        [{"name": "jira__jira_get_issue", "description": "Fetch an issue"}]
    )

    assert corpus == [("jira jira_get_issue", "Fetch an issue")]


def test_corpus_handles_a_tool_name_containing_the_separator():
    corpus = gateway_tool_search._search_corpus([{"name": "srv__weird__tool", "description": "d"}])

    assert corpus == [("srv weird__tool", "d")]


def test_corpus_handles_an_unprefixed_name():
    corpus = gateway_tool_search._search_corpus([{"name": "bare", "description": "d"}])

    assert corpus == [("bare", "d")]


@pytest.mark.asyncio
async def test_ranking_still_finds_the_right_tool_after_the_corpus_change():
    result = await execute_tool_search({"query": "create an issue", "top_k": 1}, _agg())

    assert result["tools"][0]["name"] == "github__create_issue"
