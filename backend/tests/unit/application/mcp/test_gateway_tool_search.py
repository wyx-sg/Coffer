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


async def test_a_groups_description_is_scored_and_returned():
    """A custom-tool group's description joins each of its tools' text, and comes
    back beside the tool as ``group_description``."""
    tools = [
        {"name": "acme__list_items", "description": "List items", "inputSchema": {}},
        {"name": "slack__post_message", "description": "Post a Slack message"},
    ]
    about = {"acme": "Weather forecasts for warehouse sites"}

    out = await execute_tool_search({"query": "weather forecast"}, tools, about=about)

    assert out["tools"][0]["name"] == "acme__list_items"
    assert out["tools"][0]["group_description"] == about["acme"]
    plain = await execute_tool_search({"query": "post slack message"}, tools, about=about)
    assert "group_description" not in plain["tools"][0]


def test_corpus_drops_the_duplicated_server_token():
    """`jira__jira_get_issue` tokenizes as jira, jira, get, issue — the server
    name lands twice at the ranker's name weight and crowds out the tokens that
    carry the intent."""
    corpus = gateway_tool_search._search_corpus(
        [{"name": "jira__jira_get_issue", "description": "Fetch an issue"}]
    )

    assert corpus == [("jira jira_get_issue", "Fetch an issue", "")]


def test_corpus_handles_a_tool_name_containing_the_separator():
    corpus = gateway_tool_search._search_corpus([{"name": "srv__weird__tool", "description": "d"}])

    assert corpus == [("srv weird__tool", "d", "")]


def test_corpus_handles_an_unprefixed_name():
    corpus = gateway_tool_search._search_corpus([{"name": "bare", "description": "d"}])

    assert corpus == [("bare", "d", "")]


@pytest.mark.asyncio
async def test_ranking_still_finds_the_right_tool_after_the_corpus_change():
    result = await execute_tool_search({"query": "create an issue", "top_k": 1}, _agg())

    assert result["tools"][0]["name"] == "github__create_issue"


async def test_exposure_search_breaks_a_tie_in_favour_of_the_search_only_tool():
    twins = [
        {"name": "alpha__fetch", "description": "fetch the data", "inputSchema": {}},
        {"name": "beta__fetch", "description": "fetch the data", "inputSchema": {}},
    ]

    out = await execute_tool_search(
        {"query": "fetch data"}, twins, {"alpha__fetch": "listed", "beta__fetch": "search"}
    )

    assert [t["name"] for t in out["tools"]] == ["beta__fetch", "alpha__fetch"]
    assert out["total_searched"] == 2  # every tool stays searchable


def test_corpus_carries_the_input_schema_text():
    corpus = gateway_tool_search._search_corpus(
        [
            {
                "name": "account__get_account_list",
                "description": "查询账号列表",
                "inputSchema": {"type": "object", "properties": {"phone_list": {"type": "array"}}},
            }
        ]
    )

    assert corpus == [("account get_account_list", "查询账号列表", "phone_list")]


def _mixed_language_catalogue():
    return [
        {
            "name": "crm__get_user",
            "description": "Get a user by their id",
            "inputSchema": {"type": "object", "properties": {"user_id": {"type": "string"}}},
        },
        {
            "name": "account__get_account_list",
            "description": "查询账号列表 支持批量查询",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "phone_list": {"type": "array", "description": "手机号列表"},
                    "status": {"type": "string", "enum": ["active", "frozen"]},
                },
            },
        },
        {
            "name": "order__get_order_detail",
            "description": "查询订单详情",
            "inputSchema": {"type": "object", "properties": {"order_id": {"type": "string"}}},
        },
    ]


@pytest.mark.acceptance(spec="mcp-gateway", scenario="search the catalogue in Chinese")
async def test_a_chinese_query_finds_the_tool_described_in_chinese():
    out = await execute_tool_search({"query": "查询账号列表"}, _mixed_language_catalogue())

    assert out["tools"][0]["name"] == "account__get_account_list"


@pytest.mark.acceptance(spec="mcp-gateway", scenario="search reaches a tool through its parameters")
async def test_a_query_matching_only_a_parameter_finds_the_tool():
    by_name = await execute_tool_search(
        {"query": "find a user by phone number"}, _mixed_language_catalogue()
    )
    by_enum = await execute_tool_search({"query": "frozen"}, _mixed_language_catalogue())
    by_param_description = await execute_tool_search(
        {"query": "按手机号查"}, _mixed_language_catalogue()
    )

    assert "account__get_account_list" in [t["name"] for t in by_name["tools"]]
    assert by_enum["tools"][0]["name"] == "account__get_account_list"
    assert by_param_description["tools"][0]["name"] == "account__get_account_list"
