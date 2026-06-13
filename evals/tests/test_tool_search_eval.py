from evals.tool_search_eval import run_tool_search_eval


def test_tool_search_eval_scores_well():
    report = run_tool_search_eval(top_k=3)
    assert report["suite"] == "tool_search"
    assert report["primary"]["name"] == "recall@3"
    assert report["primary"]["value"] >= 0.8
    assert report["n"] == 14
    assert "mrr" in report["secondary"]
