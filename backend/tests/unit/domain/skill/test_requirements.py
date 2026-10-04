"""Parsing SKILL.md ``requires:`` leniently: what is understood is kept, the
rest is skipped with a warning naming why (spec skill-manager "Show the
commands a skill declares it needs")."""

from __future__ import annotations

import pytest

from coffer.domain.skill.requirements import (
    CommandRequirement,
    ToolRequirement,
    parse_requires,
    required_skills_from_skill_md,
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


_TOOLS_DOC = """---
name: triage
description: Triage.
requires:
  commands: [gh]
  tools: [github, {name: billing-api, why: Reads invoices.}, "bad name", github]
metadata:
  requires: [coffer-evidence, coffer-evidence, "", 7]
---
"""


@pytest.mark.acceptance(
    spec="skill-manager", scenario="a skill's tools are read from the mapping form"
)
def test_the_mapping_form_names_tools_and_skips_what_is_not_a_name() -> None:
    parsed = requirements_from_skill_md(_TOOLS_DOC)
    assert parsed.requirements == (CommandRequirement(command="gh"),)
    assert parsed.tools == (
        ToolRequirement("github"),
        ToolRequirement("billing-api", "Reads invoices."),
    )
    assert parsed.warnings == (
        "requires tool 3: 'bad name' is not a tool name; skipped",
        "requires tool github: declared twice; later entry skipped",
    )


def test_metadata_requires_names_the_skills_a_skill_loads() -> None:
    assert required_skills_from_skill_md(_TOOLS_DOC) == ("coffer-evidence",)
    assert required_skills_from_skill_md("---\nname: a\ndescription: b\n---\n") == ()


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
    parsed = parse_requires({"commands": ["jq"], "flags": ["rg"], "env": {"A": "b"}})
    assert parsed.requirements == (CommandRequirement(command="jq"),)
    assert parsed.secrets == ()
    assert parsed.warnings == (
        "requires: unknown key(s) env, flags refused; only commands, secrets and tools are read",
    )


def _req(command: str, min_version: str | None = None) -> CommandRequirement:
    return CommandRequirement(command=command, min_version=min_version)


def _commands(value: object) -> list[CommandRequirement]:
    return list(parse_requires(value).requirements)


def _md_commands(text: str) -> list[CommandRequirement]:
    return list(requirements_from_skill_md(text).requirements)


def test_a_list_of_names_and_versioned_names_is_read_in_order() -> None:
    assert _commands(["jq", "gh>=2.40"]) == [
        _req("jq"),
        _req("gh", "2.40"),
    ]


def test_a_mapping_reads_its_commands_key() -> None:
    assert _commands({"commands": ["rg", "fd"]}) == [
        _req("rg"),
        _req("fd"),
    ]


def test_a_mapping_without_commands_declares_nothing() -> None:
    assert _commands({"flags": ["rg"]}) == []


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ({"command": "gh", "version": ">=2.40"}, _req("gh", "2.40")),
        ({"command": "gh", "version": 2}, _req("gh", "2")),
        ({"name": "jq", "min_version": "1.6"}, _req("jq", "1.6")),
        ({"command": " kubectl "}, _req("kubectl")),
        ("node == 20.1", _req("node", "20.1")),
        ("python3~=3.12", _req("python3", "3.12")),
    ],
)
def test_each_entry_spelling_is_one_requirement(
    entry: object, expected: CommandRequirement
) -> None:
    assert _commands([entry]) == [expected]


def test_a_single_string_is_one_requirement() -> None:
    assert _commands("jq") == [_req("jq")]


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
    assert _commands([junk, "jq"]) == [_req("jq")]


def test_a_value_that_is_not_a_list_declares_nothing() -> None:
    assert _commands(7) == []
    assert _commands(None) == []


def test_skill_md_frontmatter_is_read() -> None:
    text = '---\nname: x\ndescription: d\nrequires: [jq, "gh>=2.40"]\n---\nbody\n'
    assert _md_commands(text) == [
        _req("jq"),
        _req("gh", "2.40"),
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
    assert _md_commands(text) == []
