"""Smoke test for the retrieval eval — runs the real keyword index end-to-end.

Deterministic and local (FTS5, no embedding model, no network), so it is safe
to run anywhere Coffer's backend is importable.
"""

from __future__ import annotations

import asyncio

from evals.retrieval_eval import run_retrieval_eval


def test_retrieval_eval_runs_and_scores() -> None:
    report = asyncio.run(run_retrieval_eval(top_k=3))

    assert report["suite"] == "retrieval"
    assert report["n"] == 10
    assert report["primary"]["name"] == "recall@3"
    assert 0.0 <= report["primary"]["value"] <= 1.0
    # the fixture corpus is keyword-separable; keyword retrieval should ace it
    assert report["primary"]["value"] >= 0.8
    for case in report["cases"]:
        assert case["ranked"], f"empty ranking for: {case['query']}"
