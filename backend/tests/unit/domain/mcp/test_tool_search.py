# backend/tests/unit/domain/mcp/test_tool_search.py
from coffer.domain.mcp.tool_search import ScoredTool, rank_by_similarity, rank_tools


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


# -- rank_by_similarity (semantic cosine ranker) -------------------------------


def test_similarity_ranks_closest_vector_first():
    query = [1.0, 0.0]
    docs = [[0.0, 1.0], [0.9, 0.1], [0.2, 0.9]]
    ranked = rank_by_similarity(query, docs, top_k=3)
    assert ranked[0].index == 1  # most aligned with the query axis
    assert ranked[0].score > ranked[1].score


def test_similarity_skips_zero_norm_docs_and_empty_query():
    assert rank_by_similarity([0.0, 0.0], [[1.0, 0.0]], top_k=3) == []
    ranked = rank_by_similarity([1.0, 0.0], [[0.0, 0.0], [1.0, 0.0]], top_k=3)
    assert [s.index for s in ranked] == [1]  # zero-norm doc dropped


def test_similarity_ties_break_on_index_order():
    query = [1.0, 0.0]
    docs = [[1.0, 0.0], [1.0, 0.0]]
    ranked = rank_by_similarity(query, docs, top_k=2)
    assert [s.index for s in ranked] == [0, 1]
