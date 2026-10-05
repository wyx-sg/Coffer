"""The bundled rule file and how it is read into rules and allowlists
(spec secret "Detect plaintext secrets with the bundled rules")."""

from __future__ import annotations

import math
import re
import tomllib

import pytest

from coffer.infrastructure.secret import rule_set
from coffer.infrastructure.secret.rule_set import Allowlist, Rule, RuleSet, bundled, parse


def _document() -> dict[str, object]:
    with rule_set.RULES_FILE.open("rb") as f:
        return tomllib.load(f)


@pytest.mark.acceptance(spec="secret", scenario="the bundled rules say where they came from")
def test_the_bundled_rules_say_where_they_came_from() -> None:
    header = rule_set.RULES_FILE.read_text("utf-8").split("[source]")[0]
    source = _document()["source"]
    assert isinstance(source, dict)
    assert source["repository"] == "https://github.com/gitleaks/gitleaks"
    assert re.fullmatch(r"v\d+\.\d+\.\d+", source["version"])
    assert re.fullmatch(r"[0-9a-f]{40}", source["commit"])
    assert source["license"] == "MIT"
    for line in (source["version"], source["commit"], "gitleaks", "MIT"):
        assert line in header
    assert "gitleaks.LICENSE" in header
    licence = rule_set.RULES_FILE.with_name("gitleaks.LICENSE")
    assert licence.read_text("utf-8").startswith("MIT License")
    assert bundled().source == source


@pytest.mark.acceptance(spec="secret", scenario="the bundled rules say where they came from")
def test_every_rule_of_the_release_is_in_the_file_or_listed_as_untranslated() -> None:
    document = _document()
    source = document["source"]
    assert isinstance(source, dict)
    rules = document["rules"]
    assert isinstance(rules, list)
    assert source["rules"] == len(rules)
    # gitleaks v8.30.1 has 222 rules; nothing in it is out of reach of the translation.
    assert source["untranslated"] == []
    assert len(rules) + len(source["untranslated"]) == 222


def test_the_path_only_rule_is_not_a_content_rule() -> None:
    document = _document()
    with_regex = [r for r in document["rules"] if r.get("regex")]  # type: ignore[attr-defined]
    assert len(bundled().rules) == len(with_regex)
    assert len(with_regex) == len(document["rules"]) - 1  # type: ignore[arg-type]


def test_the_bundled_rule_set_is_built_once() -> None:
    assert bundled() is bundled()
    assert len({r.id for r in bundled().rules}) == len(bundled().rules)


def test_every_rule_is_ascii_only_like_re2() -> None:
    assert all(r.regex.flags & re.ASCII for r in bundled().rules)
    assert re.compile(r"\d", re.ASCII).fullmatch("٣") is None


def test_shannon_entropy_is_bits_per_character() -> None:
    assert rule_set.shannon_entropy("") == 0.0
    assert rule_set.shannon_entropy("aaaa") == 0.0
    assert rule_set.shannon_entropy("abab") == pytest.approx(1.0)
    assert rule_set.shannon_entropy("abcdefgh") == pytest.approx(math.log2(8))


def _rule(**table: object) -> Rule:
    return Rule.from_toml({"id": "t", "regex": r"k=(\w+)", **table})


def test_a_rule_reads_its_toml_table() -> None:
    rule = _rule(
        keywords=["KeyWord"],
        secretGroup=1,
        entropy=3.5,
        path=r"\.env\Z",
        allowlists=[{"stopwords": ["Sample"]}],
    )
    assert rule.keywords == ("keyword",)
    assert rule.secret_group == 1 and rule.entropy == 3.5
    assert rule.path is not None and rule.path.search("a.env")
    assert rule.allowlists[0].stopwords == ("sample",)
    assert not rule.multiline


@pytest.mark.parametrize("regex", [r"(?s:.){0,100}?x", r"-----BEGIN [\s\S-]*?-----END", r"(?s)a.b"])
def test_a_pattern_that_can_cross_lines_is_multiline(regex: str) -> None:
    assert Rule.from_toml({"id": "t", "regex": regex}).multiline


def test_the_secret_is_the_configured_group_else_the_first_nonempty_group_else_the_match() -> None:
    text = "k=abc"
    configured = Rule.from_toml({"id": "t", "regex": r"(k)=(\w+)", "secretGroup": 2})
    assert configured.secret_span(configured.regex.search(text)) == (2, 5)  # type: ignore[arg-type]
    first = Rule.from_toml({"id": "t", "regex": r"()k=(\w+)"})
    assert first.secret_span(first.regex.search(text)) == (2, 5)  # type: ignore[arg-type]
    whole = Rule.from_toml({"id": "t", "regex": r"k=\w+"})
    assert whole.secret_span(whole.regex.search(text)) == (0, 5)  # type: ignore[arg-type]


def _allow(**table: object) -> Allowlist:
    return Allowlist.from_toml(dict(table))


def test_an_allowlist_regex_reads_the_secret_by_default() -> None:
    allow = _allow(regexes=["^abc"])
    assert allow.allows("abcdef", "k=abcdef", "x k=abcdef", "")
    assert not allow.allows("xabc", "k=xabc", "k=xabc", "")


@pytest.mark.parametrize(
    ("target", "expected"),
    [("secret", False), ("match", True), ("line", True)],
)
def test_an_allowlist_regex_can_read_the_match_or_the_line(target: str, expected: bool) -> None:
    allow = _allow(regexes=["^k=|^lead"], regexTarget=target)
    assert allow.allows("value", "k=value", "lead k=value", "") is expected


def test_an_allowlist_stopword_is_matched_lowercased_inside_the_secret() -> None:
    allow = _allow(stopwords=["Example"])
    assert allow.allows("MyEXAMPLEKey", "", "", "")
    assert not allow.allows("MyKey", "", "", "")


def test_an_or_allowlist_skips_a_path_before_the_file_is_read() -> None:
    allow = _allow(paths=[r"\.lock\Z"])
    assert allow.skips_path("yarn.lock")
    assert not allow.skips_path("yarn.json")
    assert not allow.skips_path("")


def test_an_and_allowlist_needs_every_configured_check() -> None:
    allow = _allow(
        condition="and", paths=[r"\.md\Z"], regexes=["^ab"], stopwords=["cd"], regexTarget="secret"
    )
    assert allow.condition == "AND"
    assert not allow.skips_path("a.md")
    assert allow.allows("abcd", "", "", "a.md")
    assert not allow.allows("abcd", "", "", "a.txt")
    assert not allow.allows("abxx", "", "", "a.md")
    assert not allow.allows("xxcd", "", "", "a.md")
    assert not allow.allows("abcd", "", "", "")


def test_an_empty_and_allowlist_allows_nothing() -> None:
    assert not _allow(condition="AND").allows("abc", "", "", "a.md")
    assert not _allow().allows("abc", "", "", "a.md")


def test_parse_builds_rules_the_global_allowlist_and_the_source() -> None:
    parsed = parse(
        {
            "source": {"version": "v0"},
            "allowlist": {"paths": [r"\.png\Z"]},
            "rules": [{"id": "a", "regex": "x"}, {"id": "path-only", "path": r"\.pem\Z"}],
        }
    )
    assert isinstance(parsed, RuleSet)
    assert [r.id for r in parsed.rules] == ["a"]
    assert parsed.allowlist.skips_path("a.png")
    assert parsed.source == {"version": "v0"}
    assert parse({}).rules == ()
