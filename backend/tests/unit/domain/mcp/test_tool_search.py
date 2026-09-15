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
