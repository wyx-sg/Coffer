"""Unit: rules-split LLM prompt + classification parsing (no network)."""

from __future__ import annotations

import json

from coffer.application.memory.rules_split import (
    RULES_SPLIT_SYSTEM,
    build_split_user,
    parse_classification,
)


def _raw(*pairs: tuple[int, str]) -> str:
    return json.dumps({"assignments": [{"index": i, "category": c} for i, c in pairs]})


def test_parse_maps_index_to_category() -> None:
    rules = ["commit small", "branch off main", "write tests first"]
    out = parse_classification(_raw((0, "git"), (1, "git"), (2, "testing")), rules)
    assert out == {"commit small": "git", "branch off main": "git", "write tests first": "testing"}


def test_parse_strips_code_fence() -> None:
    rules = ["a rule"]
    raw = "```json\n" + _raw((0, "ops")) + "\n```"
    assert parse_classification(raw, rules) == {"a rule": "ops"}


def test_parse_malformed_returns_empty() -> None:
    assert parse_classification("not json at all", ["a", "b"]) == {}


def test_parse_ignores_out_of_range_or_incomplete() -> None:
    rules = ["only rule"]
    raw = json.dumps(
        {
            "assignments": [
                {"index": 0, "category": "x"},
                {"index": 9, "category": "y"},
                {"index": 1},
            ]
        }
    )
    assert parse_classification(raw, rules) == {"only rule": "x"}


def test_build_split_user_lists_indexed_rules() -> None:
    user = build_split_user(["alpha rule", "beta rule"])
    assert "0" in user and "alpha rule" in user
    assert "1" in user and "beta rule" in user


def test_system_prompt_is_nonempty() -> None:
    assert isinstance(RULES_SPLIT_SYSTEM, str) and RULES_SPLIT_SYSTEM.strip()
