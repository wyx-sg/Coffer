"""Tool-search eval — measures the coffer__search_tools ranker offline.

Scores the pure keyword ranker (``coffer.domain.mcp.tool_search.rank_tools``)
over a labelled set of intent → expected-tool cases against an upstream-shaped
catalogue (``<server>__<tool>`` names with near-duplicates across servers) — the
same kind of aggregated catalogue the live tool ranks. Fully local,
deterministic, free — no LLM, so it is the one suite the default ``make eval``
path runs; the tool-routing suite needs a model and is opt-in (``--routing``).
"""

from __future__ import annotations

import re

from coffer.domain.mcp.tool_search import rank_tools, schema_text
from evals._io import load_jsonl
from evals.metrics import mrr, recall_at_k

_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]")


def run_tool_search_eval(*, top_k: int = 5) -> dict:
    """Run the tool-search ranking suite; return a scorecard dict."""
    catalog = load_jsonl("tool_search_catalog.jsonl")
    queries = load_jsonl("tool_search.jsonl")
    # The same three texts the gateway scores: name, description, and the
    # input schema's parameter names, descriptions and enum values.
    catalogue = [
        (t["name"].replace("__", " ", 1), t["description"], schema_text(t.get("inputSchema")))
        for t in catalog
    ]
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
    cjk = [c for c in cases if _CJK.search(c["query"])]
    cjk_recall = sum(c["recall"] for c in cjk) / len(cjk) if cjk else 0.0
    return {
        "suite": "tool_search",
        "primary": {"name": f"recall@{top_k}", "value": round(mean_recall, 4)},
        "secondary": {
            "mrr": round(mean_mrr, 4),
            f"recall@{top_k}_cjk_queries": round(cjk_recall, 4),
            "cjk_queries": len(cjk),
        },
        "n": n,
        "cases": cases,
    }


__all__ = ["run_tool_search_eval"]
