# backend/tests/unit/application/mcp/test_gateway_tool_search.py
import pytest
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


def test_execute_returns_ranked_real_schema():
    out = execute_tool_search({"query": "create github issue"}, _agg())
    assert out["tools"][0]["name"] == "github__create_issue"
    assert "inputSchema" in out["tools"][0]
    assert out["tools"][0]["score"] > 0


def test_execute_excludes_coffer_builtins():
    out = execute_tool_search({"query": "recall memory"}, _agg())
    assert all(not t["name"].startswith("coffer__") for t in out["tools"])
    assert out["total_searched"] == 2  # coffer__recall excluded


def test_execute_clamps_top_k():
    out = execute_tool_search({"query": "post message", "top_k": 999}, _agg())
    assert len(out["tools"]) <= 2


def test_execute_rejects_empty_query():
    with pytest.raises(ValueError):
        execute_tool_search({"query": "  "}, _agg())
    with pytest.raises(ValueError):
        execute_tool_search({}, _agg())
