"""Unit: merge-scan verdict prompt building + strict JSON parsing (FR-056)."""

from __future__ import annotations

import json

from coffer.application.memory.merge_prompt import (
    MAX_SAMPLE_SLUGS,
    MAX_SAMPLE_TITLES,
    MergeVerdict,
    StoreEvidence,
    build_pair_prompt,
    parse_verdict,
)


def _evidence(store: str = "project-" + "A" * 26, **over: object) -> StoreEvidence:
    base: dict = {
        "store": store,
        "label": "Coffer",
        "root": "/repo/coffer",
        "remote": "github.com/u/coffer",
        "facts": 3,
        "fact_titles": ["deploy via make release", "api base path"],
        "topic_slugs": ["deploy", "api"],
    }
    base.update(over)
    return StoreEvidence(**base)


# ----- build_pair_prompt -----


def test_pair_prompt_carries_both_stores_evidence():
    a = _evidence(label="Coffer A")
    b = _evidence(store="project-" + "B" * 26, label="Coffer B", remote=None)
    prompt = build_pair_prompt(a, b)
    payload = json.loads(prompt.split("\n\n", 1)[1])
    assert payload["store_a"]["label"] == "Coffer A"
    assert payload["store_b"]["label"] == "Coffer B"
    assert payload["store_a"]["normalized_remote"] == "github.com/u/coffer"
    assert payload["store_b"]["normalized_remote"] is None
    assert payload["store_a"]["fact_count"] == 3


def test_pair_prompt_caps_title_and_slug_samples():
    a = _evidence(
        fact_titles=[f"t{i}" for i in range(MAX_SAMPLE_TITLES + 20)],
        topic_slugs=[f"s{i}" for i in range(MAX_SAMPLE_SLUGS + 20)],
    )
    payload = json.loads(build_pair_prompt(a, _evidence()).split("\n\n", 1)[1])
    assert len(payload["store_a"]["fact_title_sample"]) == MAX_SAMPLE_TITLES
    assert len(payload["store_a"]["topic_slug_sample"]) == MAX_SAMPLE_SLUGS


# ----- parse_verdict -----


def test_parse_valid_verdict():
    raw = '{"same_project": true, "confidence": "high", "reason": "same repo name"}'
    assert parse_verdict(raw) == MergeVerdict(
        same_project=True, confidence="high", reason="same repo name"
    )


def test_parse_strips_code_fence():
    raw = '```json\n{"same_project": false, "confidence": "low", "reason": "nope"}\n```'
    v = parse_verdict(raw)
    assert v is not None and v.same_project is False and v.confidence == "low"


def test_parse_malformed_json_returns_none():
    assert parse_verdict("the stores look similar") is None
    assert parse_verdict("{not json") is None
    assert parse_verdict("[1, 2]") is None  # not an object


def test_parse_rejects_missing_or_wrong_typed_fields():
    assert parse_verdict('{"confidence": "high", "reason": "r"}') is None  # no same_project
    assert (
        parse_verdict('{"same_project": "yes", "confidence": "high", "reason": "r"}') is None
    )  # non-bool
    assert (
        parse_verdict('{"same_project": true, "confidence": "certain", "reason": "r"}') is None
    )  # invalid confidence (certain is reserved for the deterministic tier)
    assert (
        parse_verdict('{"same_project": true, "confidence": "high", "reason": "  "}') is None
    )  # blank reason
