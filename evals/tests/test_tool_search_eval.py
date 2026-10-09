from evals.tool_search_eval import run_tool_search_eval


def test_tool_search_eval_scores_well():
    report = run_tool_search_eval(top_k=5)
    assert report["suite"] == "tool_search"
    assert report["primary"]["name"] == "recall@5"
    assert report["primary"]["value"] >= 0.7
    assert report["n"] >= 80
    assert "mrr" in report["secondary"]


def test_tool_search_eval_scores_chinese_queries_on_their_own():
    report = run_tool_search_eval(top_k=5)
    assert report["secondary"]["cjk_queries"] >= 25
    assert report["secondary"]["recall@5_cjk_queries"] >= 0.7
