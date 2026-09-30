"""Parsing SKILL.md ``requires:`` leniently: what is understood is kept, the
rest is skipped with a warning naming why."""

from __future__ import annotations

from coffer.domain.skill.requirements import (
    CommandRequirement,
    parse_requires,
    requirements_from_skill_md,
)

_DOC = """---
name: issues
description: Files issues.
requires:
  - command: gh
    title: GitHub CLI
    min_version: "2.40"
    login_check: gh auth status
    login: gh auth login
    brew: gh
    why: Opens and labels issues.
  - jq
---
# body
"""


def test_a_full_entry_and_a_bare_name() -> None:
    parsed = requirements_from_skill_md(_DOC)
    assert parsed.warnings == ()
    assert parsed.requirements == (
        CommandRequirement(
            command="gh",
            title="GitHub CLI",
            min_version="2.40",
            login_check=("gh", "auth", "status"),
            login="gh auth login",
            brew="gh",
            why="Opens and labels issues.",
        ),
        CommandRequirement(command="jq"),
    )


def test_no_frontmatter_or_no_requires_is_empty() -> None:
    assert requirements_from_skill_md("# no frontmatter").requirements == ()
    assert requirements_from_skill_md("---\nname: a\n---\n").requirements == ()


def test_a_path_is_skipped() -> None:
    parsed = parse_requires(["/usr/bin/jq"])
    assert parsed.requirements == ()
    assert "is a path" in parsed.warnings[0]


def test_a_login_check_running_another_program_is_skipped() -> None:
    parsed = parse_requires([{"command": "gh", "login_check": "curl evil.example"}])
    assert parsed.requirements == ()
    assert "'curl'" in parsed.warnings[0] and "'gh'" in parsed.warnings[0]


def test_a_login_check_may_be_a_list() -> None:
    parsed = parse_requires([{"command": "gh", "login_check": ["gh", "auth", "status"]}])
    assert parsed.requirements[0].login_check == ("gh", "auth", "status")


def test_an_unquoted_float_minimum_is_skipped() -> None:
    # YAML reads 2.40 as 2.4, which is a different minimum.
    parsed = parse_requires([{"command": "gh", "min_version": 2.40}])
    assert parsed.requirements == ()
    assert "quoted" in parsed.warnings[0]


def test_an_integer_minimum_is_kept() -> None:
    [req] = parse_requires([{"command": "node", "min_version": 20}]).requirements
    assert req.min_version == "20"


def test_a_bad_formula_is_skipped() -> None:
    parsed = parse_requires([{"command": "gh", "brew": "gh; echo hi"}])
    assert parsed.requirements == ()
    assert "formula" in parsed.warnings[0]


def test_a_tapped_formula_is_kept() -> None:
    parsed = parse_requires([{"command": "tool", "brew": "owner/tap/tool@2"}])
    assert parsed.requirements[0].brew == "owner/tap/tool@2"


def test_no_command_and_wrong_shapes_are_skipped() -> None:
    parsed = parse_requires([{"title": "x"}, 3, ""])
    assert parsed.requirements == ()
    assert len(parsed.warnings) == 3


def test_not_a_list_is_one_warning() -> None:
    parsed = parse_requires(7)
    assert parsed.requirements == ()
    assert parsed.warnings == ("requires: expected a list of commands; ignored",)


def test_unknown_fields_are_ignored_with_a_warning_and_the_entry_kept() -> None:
    parsed = parse_requires([{"command": "gh", "install": "make it"}])
    assert parsed.requirements == (CommandRequirement(command="gh"),)
    assert "unknown field(s) install" in parsed.warnings[0]


def test_a_command_named_twice_keeps_the_first() -> None:
    parsed = parse_requires([{"command": "gh", "brew": "gh"}, "gh"])
    assert parsed.requirements == (CommandRequirement(command="gh", brew="gh"),)
    assert "declared twice" in parsed.warnings[0]
