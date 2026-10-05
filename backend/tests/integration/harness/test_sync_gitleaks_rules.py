"""``scripts/sync_gitleaks_rules.py``: the translation from Go RE2 to Python ``re``
and the rule file it writes, on fixed rule fragments, never the network
(spec secret "Detect plaintext secrets with the bundled rules")."""

from __future__ import annotations

import re
import runpy
import tomllib
from pathlib import Path
from typing import Any

import pytest

from coffer.infrastructure.secret import rule_set

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "sync_gitleaks_rules.py"
S = runpy.run_path(str(_SCRIPT))
translate = S["translate"]
convert = S["convert"]
render = S["render"]
Untranslatable = S["UntranslatableError"]
COMMIT = "0123456789abcdef0123456789abcdef01234567"


def test_a_flag_group_in_the_middle_is_reopened_across_alternation() -> None:
    assert translate("(?:a(?i)b|c)") == "(?:a(?i:b)|(?i:c))"
    out = re.compile(translate("(?:a(?i)b|c)"), re.ASCII)
    assert out.fullmatch("aB") and out.fullmatch("C") and not out.fullmatch("A")


def test_a_leading_flag_group_is_kept_as_it_is() -> None:
    assert translate("(?i)abc") == "(?i)abc"


def test_a_flag_group_closes_with_its_enclosing_group() -> None:
    out = re.compile(translate("(a(?i)b)c"), re.ASCII)
    assert out.fullmatch("aBc") and not out.fullmatch("aBC")


def test_end_of_text_is_python_end_of_text() -> None:
    assert translate(r"abc\z") == r"abc\Z"
    assert translate("abc$") == r"abc\Z"
    out = re.compile(translate("abc$"), re.ASCII)
    assert out.search("abc") and not out.search("abc\n")
    assert translate(r"a[$]b") == "a[$]b"


@pytest.mark.parametrize(
    ("posix", "text"),
    [
        ("alnum", "aZ9"),
        ("alpha", "aZ"),
        ("digit", "09"),
        ("xdigit", "09afAF"),
        ("upper", "AZ"),
        ("lower", "az"),
        ("punct", "!/:@[`{~"),
        ("space", " \t\n"),
    ],
)
def test_posix_classes_become_ascii_ranges(posix: str, text: str) -> None:
    out = translate(f"[[:{posix}:]]+")
    assert "[:" not in out
    assert re.compile(out, re.ASCII).fullmatch(text)


def test_a_posix_class_mixes_with_other_members() -> None:
    out = re.compile(translate(r"[[:alnum:]_\-]{3}"), re.ASCII)
    assert out.fullmatch("a_-") and not out.fullmatch("a b")


def test_classes_are_ascii_like_re2() -> None:
    out = re.compile(translate(r"\w+"), re.ASCII)
    assert out.fullmatch("abc_1") and not out.fullmatch("é")
    assert not re.compile(translate(r"\d"), re.ASCII).fullmatch("٣")


def test_a_set_operator_character_is_read_literally() -> None:
    # RE2: the class is ``[a-z[&&]`` (its members include ``[`` and ``&``), then ``]+``.
    out = re.compile(translate("[a-z[&&]]+"), re.ASCII)
    assert out.fullmatch("a]") and out.fullmatch("&]]") and not out.fullmatch("a")


def test_a_named_group_keeps_its_name() -> None:
    assert re.compile(translate(r"(?P<n>a)(?<m>b)"), re.ASCII).fullmatch("ab")


@pytest.mark.parametrize(
    "pattern",
    [r"\p{L}+", r"\PL", r"[\p{L}]", r"[[:^alpha:]]", "(?m)^a", "(?m:^a)", r"\Qa.b\E", r"a\C", "(a"],
)
def test_an_untranslatable_construct_is_refused(pattern: str) -> None:
    with pytest.raises(Untranslatable):
        translate(pattern)


def _config() -> dict[str, Any]:
    return {
        "allowlist": {"paths": [r"\.png$"], "regexes": [r"(?:a(?i)b|c)"], "stopwords": ["x"]},
        "rules": [
            {
                "id": "good",
                "regex": r"tok_([[:alnum:]]{8})\z",
                "keywords": ["tok_"],
                "entropy": 3.5,
                "secretGroup": 1,
                "path": r"\.env$",
                "allowlists": [{"regexes": [r"^x(?i)y"], "regexTarget": "match"}],
            },
            {"id": "unicode", "regex": r"\p{L}{4}"},
            {"id": "multiline", "regex": "(?m)^a"},
            {"id": "bad-allowlist", "regex": "a", "allowlists": [{"paths": [r"\p{L}"]}]},
            {"id": "path-only", "path": r"\.pem$"},
        ],
    }


def test_convert_translates_every_pattern_and_lists_the_rest() -> None:
    converted, untranslated = convert(_config())
    assert [r["id"] for r in converted["rules"]] == ["good", "path-only"]
    good = converted["rules"][0]
    assert good["regex"] == r"tok_([a-zA-Z0-9]{8})\Z"
    assert good["path"] == r"\.env\Z"
    assert good["allowlists"][0]["regexes"] == [r"^x(?i:y)"]
    assert good["entropy"] == 3.5 and good["secretGroup"] == 1
    assert converted["allowlist"]["paths"] == [r"\.png\Z"]
    assert converted["allowlist"]["regexes"] == ["(?:a(?i:b)|(?i:c))"]
    assert dict(untranslated) == {
        "unicode": "\\p",
        "multiline": "(?m)",
        "bad-allowlist": "\\p",
    }


def test_convert_does_not_change_its_input() -> None:
    config = _config()
    convert(config)
    assert config["rules"][0]["regex"] == r"tok_([[:alnum:]]{8})\z"


def _rendered() -> tuple[str, dict[str, Any]]:
    converted, untranslated = convert(_config())
    text = render(converted, "v9.9.9", COMMIT, untranslated)
    return text, tomllib.loads(text)


def test_render_names_the_source_the_release_the_commit_and_the_licence() -> None:
    text, doc = _rendered()
    header = text.split("[source]")[0]
    assert "gitleaks" in header and "v9.9.9" in header and COMMIT in header and "MIT" in header
    assert "gitleaks.LICENSE" in header
    assert doc["source"]["repository"] == "https://github.com/gitleaks/gitleaks"
    assert doc["source"]["version"] == "v9.9.9"
    assert doc["source"]["commit"] == COMMIT
    assert doc["source"]["license"] == "MIT"


def test_render_lists_the_untranslated_rules_in_the_source_table() -> None:
    _, doc = _rendered()
    assert doc["source"]["rules"] == 2
    assert doc["source"]["untranslated"] == [
        "unicode: \\p",
        "multiline: (?m)",
        "bad-allowlist: \\p",
    ]


def test_render_is_deterministic_toml_that_round_trips_through_the_rule_set() -> None:
    text, doc = _rendered()
    assert text == _rendered()[0]
    parsed = rule_set.parse(doc)
    assert [r.id for r in parsed.rules] == ["good"]
    rule = parsed.rules[0]
    assert rule.regex.pattern == r"tok_([a-zA-Z0-9]{8})\Z"
    assert rule.secret_group == 1 and rule.entropy == 3.5 and rule.keywords == ("tok_",)
    assert rule.path is not None and rule.path.search("a.env")
    assert rule.allowlists[0].target == "match"
    assert parsed.allowlist.skips_path("a.png") and not parsed.allowlist.skips_path("a.png.txt")
    assert parsed.source["version"] == "v9.9.9"


def test_render_writes_a_pattern_with_quotes_and_backslashes_exactly() -> None:
    tricky = "[`'\"\\s;]|\\\\[nr]|\\z"
    config = {"allowlist": {}, "rules": [{"id": "q", "regex": f"a(?:{tricky})"}]}
    converted, untranslated = convert(config)
    doc = tomllib.loads(render(converted, "v1", COMMIT, untranslated))
    assert doc["rules"][0]["regex"] == converted["rules"][0]["regex"]


def test_the_shipped_file_is_what_the_script_renders_from_its_own_rules() -> None:
    """Translating an already-translated pattern changes nothing the executor
    reads: the file on disk compiles and its rules keep their ids."""
    with rule_set.RULES_FILE.open("rb") as f:
        doc = tomllib.load(f)
    again, untranslated = convert(doc)
    assert untranslated == []
    assert [r["id"] for r in again["rules"]] == [r["id"] for r in doc["rules"]]
