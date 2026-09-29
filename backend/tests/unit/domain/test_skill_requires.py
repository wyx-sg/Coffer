"""``requires`` in a SKILL.md's frontmatter (spec skill-manager "Show the
commands a skill declares it needs")."""

from __future__ import annotations

import pytest

from coffer.domain.skill.requires import SkillRequirement, parse_requires, requires_from_skill_md


def test_a_list_of_names_and_versioned_names_is_read_in_order() -> None:
    assert parse_requires(["jq", "gh>=2.40"]) == [
        SkillRequirement("jq"),
        SkillRequirement("gh", "2.40"),
    ]


def test_a_mapping_reads_its_commands_key() -> None:
    assert parse_requires({"commands": ["rg", "fd"]}) == [
        SkillRequirement("rg"),
        SkillRequirement("fd"),
    ]


def test_a_mapping_without_commands_declares_nothing() -> None:
    assert parse_requires({"tools": ["rg"]}) == []


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ({"command": "gh", "version": ">=2.40"}, SkillRequirement("gh", "2.40")),
        ({"command": "gh", "version": 2}, SkillRequirement("gh", "2")),
        ({"name": "jq", "min_version": "1.6"}, SkillRequirement("jq", "1.6")),
        ({"command": " kubectl "}, SkillRequirement("kubectl")),
        ("node == 20.1", SkillRequirement("node", "20.1")),
        ("python3~=3.12", SkillRequirement("python3", "3.12")),
    ],
)
def test_each_entry_spelling_is_one_requirement(entry: object, expected: SkillRequirement) -> None:
    assert parse_requires([entry]) == [expected]


def test_a_single_string_is_one_requirement() -> None:
    assert parse_requires("jq") == [SkillRequirement("jq")]


@pytest.mark.parametrize(
    "junk",
    [
        42,
        None,
        ["a", "b"],
        {"version": "1"},
        {"command": 3},
        "has space",
        "/usr/bin/jq",
        "",
        "-rf",
    ],
)
def test_an_entry_naming_no_command_is_dropped(junk: object) -> None:
    assert parse_requires([junk, "jq"]) == [SkillRequirement("jq")]


def test_a_value_that_is_not_a_list_declares_nothing() -> None:
    assert parse_requires(7) == []
    assert parse_requires(None) == []


def test_a_command_listed_twice_is_kept_once_first_spelling_wins() -> None:
    assert parse_requires(["gh>=2.40", "gh", {"command": "gh", "version": "3"}]) == [
        SkillRequirement("gh", "2.40")
    ]


def test_skill_md_frontmatter_is_read() -> None:
    text = '---\nname: x\ndescription: d\nrequires: [jq, "gh>=2.40"]\n---\nbody\n'
    assert requires_from_skill_md(text) == [
        SkillRequirement("jq"),
        SkillRequirement("gh", "2.40"),
    ]


@pytest.mark.parametrize(
    "text",
    [
        "no frontmatter at all\n",
        "",
        "---\nname: x\n",  # never closed
        "---\n: [unbalanced\n---\n",  # not YAML
        "---\n- a list\n---\n",  # not a mapping
        "---\nname: x\n---\n",  # no requires
    ],
)
def test_skill_md_without_a_readable_requires_declares_nothing(text: str) -> None:
    assert requires_from_skill_md(text) == []
