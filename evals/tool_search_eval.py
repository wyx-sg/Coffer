"""Tool-search eval — measures the coffer__search_tools ranker offline.

Scores the pure keyword ranker (``coffer.domain.mcp.tool_search.rank_tools``)
over a labelled set of intent → expected-tool cases against an upstream-shaped
catalogue (``<server>__<tool>`` names with near-duplicates across servers) — the
same kind of aggregated catalogue the live tool ranks. Fully local,
deterministic, free — no LLM, so it runs in the default ``make eval`` path
alongside the retrieval suite.
"""

from __future__ import annotations

from coffer.domain.mcp.tool_search import rank_tools

from evals._io import load_jsonl
from evals.metrics import mrr, recall_at_k


def run_tool_search_eval(*, top_k: int = 3) -> dict:
    """Run the tool-search ranking suite; return a scorecard dict."""
    catalog = load_jsonl("tool_search_catalog.jsonl")
    queries = load_jsonl("tool_search.jsonl")
    catalogue = [(t["name"], t["description"]) for t in catalog]
    names = [t["name"] for t in catalog]

    cases: list[dict] = []
    for q in queries:
        expected = set(q["expected"])
        ranked_tools = rank_tools(q["query"], catalogue, top_k)
        ranked = [names[s.index] for s in ranked_tools]
        cases.append(
            {
                "query": q["query"],
                "expected": sorted(expected),
                "ranked": ranked,
                "recall": recall_at_k(ranked, expected, k=top_k),
                "mrr": mrr(ranked, expected),
            }
        )

    n = len(cases)
    mean_recall = sum(c["recall"] for c in cases) / n if n else 0.0
    mean_mrr = sum(c["mrr"] for c in cases) / n if n else 0.0
    return {
        "suite": "tool_search",
        "primary": {"name": f"recall@{top_k}", "value": round(mean_recall, 4)},
        "secondary": {"mrr": round(mean_mrr, 4)},
        "n": n,
        "cases": cases,
    }


__all__ = ["run_tool_search_eval"]
