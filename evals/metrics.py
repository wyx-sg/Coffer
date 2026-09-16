"""Ranking metrics for the eval harness: recall@k and MRR.

Pure functions over a ranked list of result ids and the set of relevant ids.
Kept dependency-free so they are trivially testable and reusable by any suite
that produces a ranking — today that is the tool-search suite, which scores
both of them.
"""

from __future__ import annotations

from collections.abc import Sequence


def recall_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    """Fraction of the relevant ids that appear in the top-``k`` results.

    Returns 1.0 when nothing is relevant (vacuously satisfied, avoids div-by-zero).
    """
    if not relevant:
        return 1.0
    top = set(ranked[:k])
    return len(top & relevant) / len(relevant)


def mrr(ranked: Sequence[str], relevant: set[str]) -> float:
    """Reciprocal rank of the first relevant result (1-indexed); 0.0 if none."""
    for i, doc in enumerate(ranked, start=1):
        if doc in relevant:
            return 1.0 / i
    return 0.0
