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
