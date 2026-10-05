"""Every imported gitleaks rule finds a sample of its own and misses a short one
(spec secret "Detect plaintext secrets with the bundled rules").

The samples exist only in memory: ``regex_samples`` walks each translated
pattern and builds a match, shortening the secret one character below its
minimum width for the negative. A rule it cannot round-trip uses the hand
sample of ``gitleaks_hand_samples``; a rule with neither fails here, so a
refreshed rule file cannot ship an untested rule.

Each rule runs alone (the other rules would shadow a value two rules find),
then the whole rule set must still find the positive.
"""

from __future__ import annotations

import random

import pytest

from coffer.infrastructure.secret import detector
from coffer.infrastructure.secret.rule_set import Rule, RuleSet, bundled
from tests.support.gitleaks_hand_samples import HAND
from tests.support.regex_samples import Sample, generate, min_width

RULES = {r.id: r for r in bundled().rules}
#: Seeds tried per rule before a rule counts as ungeneratable.
SEEDS = 30


def _alone(rule: Rule) -> RuleSet:
    return RuleSet(rules=(rule,), allowlist=bundled().allowlist)


def _secret_group(rule: Rule, sample: Sample) -> int:
    if rule.secret_group and rule.secret_group in sample.groups:
        return rule.secret_group
    return next((g for g in sorted(sample.groups) if sample.groups[g][1] > sample.groups[g][0]), 0)


def _found(rule: Rule, text: str, path: str) -> bool:
    return any(d.rule == rule.id for d in detector.detect(text, path, _alone(rule)))


def _generated(rule: Rule, seed: int) -> tuple[str, str, str] | None:
    """``(path, positive, negative)`` built from one seed, or ``None`` when
    the pattern did not produce a match."""
    rng = random.Random(f"{rule.id}:{seed}")
    sample = generate(rule.regex, rng)
    text, offset = sample.text, 0
    if rule.keywords and not any(k in text.lower() for k in rule.keywords):
        prefix = rule.keywords[0] + " "
        text, offset = prefix + text, len(prefix)
    if not rule.regex.search(text):
        return None
    group = _secret_group(rule, sample)
    start, end = sample.groups[group] if group else (0, len(sample.text))
    width = min_width(rule.regex, group)
    if width < 1:
        return None
    short = text[: start + offset] + text[start + offset : end + offset][: width - 1]
    path = "x" + generate(rule.path, rng).text if rule.path else ""
    return path, text, short + text[end + offset :]


def _round_trip(rule: Rule) -> tuple[str, str, str] | None:
    for seed in range(SEEDS):
        built = _generated(rule, seed)
        if built and _found(rule, built[1], built[0]) and not _found(rule, built[2], built[0]):
            return built
    return None


@pytest.mark.parametrize("rule_id", sorted(RULES))
def test_rule_finds_its_sample_and_misses_a_short_one(rule_id: str) -> None:
    rule = RULES[rule_id]
    built = _round_trip(rule)
    if built is None:
        hand = HAND.get(rule_id)
        assert hand is not None, f"{rule_id}: no generated sample round-trips and no hand sample"
        built = (hand.path, hand.positive, hand.negative)
    path, positive, negative = built
    assert _found(rule, positive, path)
    assert not _found(rule, negative, path)
    # Alone it is found; with every rule it is still a finding (a value two
    # rules find is one finding, named by the other).
    assert detector.detect(positive, path)


@pytest.mark.parametrize("rule_id", sorted(HAND))
def test_hand_samples_round_trip(rule_id: str) -> None:
    hand = HAND[rule_id]
    rule = RULES[rule_id]
    assert _found(rule, hand.positive, hand.path)
    assert not _found(rule, hand.negative, hand.path)
    assert [d.rule for d in detector.detect(hand.positive, hand.path) if d.rule == rule_id] == [
        rule_id
    ]


def test_hand_samples_are_for_bundled_rules() -> None:
    assert set(HAND) <= set(RULES)


def test_a_path_condition_is_part_of_the_rule() -> None:
    hand = HAND["kubernetes-secret-yaml"]

    def names(path: str) -> list[str]:
        return [d.rule for d in detector.detect(hand.positive, path)]

    assert "kubernetes-secret-yaml" in names("secret.yaml")
    assert "kubernetes-secret-yaml" not in names("notes.md")
    assert "kubernetes-secret-yaml" not in names("")
