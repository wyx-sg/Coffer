"""Unit tests for the eval metric functions (pure, deterministic)."""

from __future__ import annotations

import math

from evals.metrics import mrr, precision_at_k, recall_at_k


def test_recall_at_k_full_hit() -> None:
    # all 2 relevant docs appear within the top-3 ranked results
    ranked = ["d3", "d1", "d2", "d9"]
    relevant = {"d1", "d2"}
    assert recall_at_k(ranked, relevant, k=3) == 1.0


def test_recall_at_k_partial() -> None:
    ranked = ["d3", "d1", "d9", "d2"]
    relevant = {"d1", "d2"}
    # only d1 is in the top-2 -> 1/2
    assert recall_at_k(ranked, relevant, k=2) == 0.5


def test_recall_at_k_no_relevant_defined_is_one() -> None:
    # nothing to retrieve -> vacuously perfect (avoid div-by-zero)
    assert recall_at_k(["a"], set(), k=3) == 1.0


def test_precision_at_k() -> None:
    ranked = ["d1", "x", "d2", "y"]
    relevant = {"d1", "d2"}
    # 1 of the top-2 is relevant -> 0.5
    assert precision_at_k(ranked, relevant, k=2) == 0.5


def test_mrr_first_relevant_rank() -> None:
    # first relevant doc is at rank 2 -> reciprocal rank 1/2
    assert mrr(["x", "d1", "d2"], {"d1", "d2"}) == 0.5


def test_mrr_none_found_is_zero() -> None:
    assert mrr(["x", "y"], {"d1"}) == 0.0


def test_mrr_first_position() -> None:
    assert math.isclose(mrr(["d1", "x"], {"d1"}), 1.0)
