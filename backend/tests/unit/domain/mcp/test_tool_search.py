# backend/tests/unit/domain/mcp/test_tool_search.py
from coffer.domain.mcp.tool_search import ScoredTool, rank_tools


def _cat():
    return [
        ("github__create_issue", "Create a new issue in a GitHub repository"),
        ("slack__post_message", "Post a message to a Slack channel"),
        ("github__search_code", "Search code across GitHub repositories"),
    ]


def test_exact_name_token_ranks_first():
    ranked = rank_tools("post a slack message", _cat(), top_k=3)
    assert ranked[0].index == 1  # slack__post_message


def test_returns_scoredtool_with_positive_score():
    ranked = rank_tools("github issue", _cat(), top_k=3)
    assert isinstance(ranked[0], ScoredTool)
    assert ranked[0].index == 0
    assert ranked[0].score > 0


def test_top_k_limits_results():
    ranked = rank_tools("github", _cat(), top_k=1)
    assert len(ranked) == 1


def test_no_match_returns_empty():
    assert rank_tools("kubernetes helm chart", _cat(), top_k=3) == []


def test_empty_catalogue_or_query_returns_empty():
    assert rank_tools("anything", [], top_k=3) == []
    assert rank_tools("", _cat(), top_k=3) == []
    assert rank_tools("github", _cat(), top_k=0) == []


def test_ties_break_on_catalogue_order():
    cat = [("a__x", "same words here"), ("b__y", "same words here")]
    ranked = rank_tools("same words", cat, top_k=2)
    assert [s.index for s in ranked] == [0, 1]


def test_an_unchanged_catalogue_is_indexed_once_and_a_changed_one_again():
    """The query-independent half of BM25 is memoised on the catalogue; the
    ranking must be identical either way, and a changed description must
    not be answered from the stale index."""
    from coffer.domain.mcp.tool_search import _index

    _index.cache_clear()
    catalogue = [("jira__create_issue", "Create a Jira issue"), ("fs__read", "Read a file")]
    first = rank_tools("jira issue", catalogue, top_k=5)
    second = rank_tools("read file", list(catalogue), top_k=5)
    assert _index.cache_info().misses == 1 and _index.cache_info().hits == 1
    assert first == rank_tools("jira issue", catalogue, top_k=5)

    changed = [("jira__create_issue", "Create a Jira issue"), ("fs__read", "Open a document")]
    assert rank_tools("read file", changed, top_k=5) != second
    assert _index.cache_info().misses == 2


def test_a_search_only_tool_goes_ahead_of_an_equal_one_the_agent_already_sees():
    twins = [("alpha__fetch", "fetch the data"), ("beta__fetch", "fetch the data")]

    plain = rank_tools("fetch data", twins, top_k=2)
    preferred = rank_tools("fetch data", twins, top_k=2, prefer=[False, True])

    assert [s.index for s in plain] == [0, 1]
    assert [s.index for s in preferred] == [1, 0]


def test_a_chinese_query_finds_a_tool_described_in_chinese():
    cat = [
        ("account__get_account_list", "查询账号列表 可按手机号批量查询"),
        ("order__get_order", "查询订单详情"),
        ("github__create_issue", "Create a new issue in a GitHub repository"),
    ]

    ranked = rank_tools("查询账号列表", cat, top_k=3)

    assert ranked[0].index == 0


def test_cjk_text_is_cut_into_character_pairs():
    from coffer.domain.mcp.tool_search import _tokenize

    assert _tokenize("查询账号") == ["查询", "询账", "账号"]
    assert _tokenize("按 ID 查") == ["按", "id", "查"]
    assert _tokenize("在GitHub上建issue") == ["在", "git", "hub", "上建", "issue"]


def test_full_width_text_is_folded_before_tokenizing():
    from coffer.domain.mcp.tool_search import _tokenize

    full_width = "".join(chr(ord(c) + 0xFEE0) for c in "GitHub") + "\u3000Issue"

    assert _tokenize(full_width) == ["git", "hub", "issue"]


def test_a_parameter_name_reaches_a_tool_its_name_and_description_miss():
    cat = [
        ("crm__get_user", "Get a user by id", "user_id"),
        ("account__get_account_list", "List accounts", "phone_list\nemail_list"),
    ]

    ranked = rank_tools("phone", cat, top_k=2)

    assert [s.index for s in ranked] == [1]


def test_parameter_text_weighs_less_than_the_description():
    cat = [
        ("a__one", "export a report", ""),
        ("b__two", "something else", "report"),
    ]

    ranked = rank_tools("report", cat, top_k=2)

    assert [s.index for s in ranked] == [0, 1]


def test_schema_text_collects_names_descriptions_and_enums_at_any_depth():
    from coffer.domain.mcp.tool_search import schema_text

    schema = {
        "type": "object",
        "properties": {
            "phone_list": {
                "type": "array",
                "description": "手机号列表",
                "items": {"type": "string"},
            },
            "status": {"type": "string", "enum": ["open", "closed", 3]},
            "filter": {
                "type": "object",
                "properties": {"region": {"type": "string"}},
            },
            "rows": {
                "type": "array",
                "items": {"type": "object", "properties": {"sku": {"type": "string"}}},
            },
        },
    }

    assert schema_text(schema).split("\n") == [
        "phone_list",
        "手机号列表",
        "status",
        "open",
        "closed",
        "filter",
        "region",
        "rows",
        "sku",
    ]
    assert schema_text(None) == ""
    assert schema_text({"type": "object"}) == ""
