"""Unit tests for the routing aggregation (pure — no model server needed)."""

from __future__ import annotations

from evals.routing_eval import aggregate_routing


def test_all_correct() -> None:
    cases = [{"correct_count": 3}, {"correct_count": 3}]
    assert aggregate_routing(cases, samples=3) == {
        "accuracy": 1.0,
        "pass^k": 1.0,
        "pass@k": 1.0,
    }


def test_mixed_reliability() -> None:
    # case A: 3/3 correct (reliable); case B: 1/3 correct (right but flaky)
    agg = aggregate_routing([{"correct_count": 3}, {"correct_count": 1}], samples=3)
    assert agg["accuracy"] == round(4 / 6, 4)
    assert agg["pass^k"] == 0.5  # only A is right every time
    assert agg["pass@k"] == 1.0  # both right at least once


def test_none_correct() -> None:
    assert aggregate_routing(
        [{"correct_count": 0}, {"correct_count": 0}], samples=3
    ) == {
        "accuracy": 0.0,
        "pass^k": 0.0,
        "pass@k": 0.0,
    }


def test_empty() -> None:
    assert aggregate_routing([], samples=3) == {
        "accuracy": 0.0,
        "pass^k": 0.0,
        "pass@k": 0.0,
    }
