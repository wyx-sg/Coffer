"""Unit tests for the SKILL.md frontmatter model (agentskills.io alignment)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from coffer.domain.skill.frontmatter import (
    _DESCRIPTION_MAX,
    FrontmatterNameError,
    SkillFrontmatter,
    rewrite_name,
    validate_frontmatter_name,
)


def test_minimum_fields_parse():
    fm = SkillFrontmatter.model_validate({"name": "my-skill", "description": "x"})
    assert fm.name == "my-skill"
    assert fm.description == "x"
    # Optional standard fields default to absent, not interpreted.
    assert fm.license is None
    assert fm.allowed_tools is None


def test_description_at_cap_is_ok():
    fm = SkillFrontmatter.model_validate({"name": "s", "description": "d" * _DESCRIPTION_MAX})
    assert len(fm.description) == _DESCRIPTION_MAX


def test_description_over_cap_rejected():
    with pytest.raises(ValidationError):
        SkillFrontmatter.model_validate({"name": "s", "description": "d" * (_DESCRIPTION_MAX + 1)})


def test_license_recognized():
    fm = SkillFrontmatter.model_validate({"name": "s", "description": "d", "license": "MIT"})
    assert fm.license == "MIT"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(2024, "2024"), (True, "True"), (1.0, "1.0")],
)
def test_license_non_string_scalar_coerced(raw, expected):
    # Unquoted YAML scalars (a year, a bool, a version) must not reject the skill.
    fm = SkillFrontmatter.model_validate({"name": "s", "description": "d", "license": raw})
    assert fm.license == expected


def test_license_non_scalar_tolerated_as_none():
    fm = SkillFrontmatter.model_validate(
        {"name": "s", "description": "d", "license": {"name": "MIT"}}
    )
    assert fm.license is None


def test_allowed_tools_list_parsed():
    fm = SkillFrontmatter.model_validate(
        {"name": "s", "description": "d", "allowed-tools": ["Bash", "Read"]}
    )
    assert fm.allowed_tools == ["Bash", "Read"]


def test_allowed_tools_comma_string_coerced():
    fm = SkillFrontmatter.model_validate(
        {"name": "s", "description": "d", "allowed-tools": "Bash, Read , Edit"}
    )
    assert fm.allowed_tools == ["Bash", "Read", "Edit"]


def test_allowed_tools_whitespace_string_coerced():
    fm = SkillFrontmatter.model_validate(
        {"name": "s", "description": "d", "allowed-tools": "Bash  Read\nEdit"}
    )
    assert fm.allowed_tools == ["Bash", "Read", "Edit"]


def test_allowed_tools_garbage_tolerated_as_none():
    # An unexpected shape must not reject an otherwise-valid skill.
    fm = SkillFrontmatter.model_validate(
        {"name": "s", "description": "d", "allowed-tools": {"unexpected": "mapping"}}
    )
    assert fm.allowed_tools is None


def test_allowed_tools_empty_collapses_to_none():
    fm = SkillFrontmatter.model_validate(
        {"name": "s", "description": "d", "allowed-tools": ["", "   "]}
    )
    assert fm.allowed_tools is None


def test_allowed_tools_accepts_field_name_alias():
    # populate_by_name lets a skill use the snake_case spelling too.
    fm = SkillFrontmatter.model_validate(
        {"name": "s", "description": "d", "allowed_tools": ["Bash"]}
    )
    assert fm.allowed_tools == ["Bash"]


def test_unknown_extra_fields_tolerated():
    fm = SkillFrontmatter.model_validate(
        {"name": "s", "description": "d", "metadata": {"k": "v"}, "future": 1}
    )
    # Tolerated, not dropped: still reachable for forward-compatibility.
    assert fm.model_dump()["metadata"] == {"k": "v"}


# ----- validate_frontmatter_name -----


@pytest.mark.parametrize("name", ["my-skill", "a", "s_1", "0abc", "a" * 64])
def test_frontmatter_name_accepts_the_standard_charset(name):
    validate_frontmatter_name(name)  # does not raise


@pytest.mark.parametrize(
    "name",
    [
        "My.Skill",  # the exact shape the FRAMEWORK rule lets through
        "MySkill",  # uppercase
        "my.skill",  # dot
        "-leading",  # must start alphanumeric
        "",
        "a" * 65,
    ],
)
def test_frontmatter_name_rejects_what_the_framework_rule_would_allow(name):
    """The kind's rule is narrower than the framework's on purpose.

    ``My.Skill`` satisfies ``^[a-zA-Z0-9_.-]{1,64}$`` and would be a perfectly
    good directory name, but Coffer writes the name into SKILL.md and its own
    importer would then reject the file it just wrote.
    """
    with pytest.raises(FrontmatterNameError):
        validate_frontmatter_name(name)


# ----- rewrite_name -----


def test_rewrite_name_changes_only_the_name_line():
    text = (
        "---\n"
        "# a comment the user wrote\n"
        "description: keep me\n"
        "name: before\n"
        "allowed-tools: [Bash]\n"
        "future-field: 1\n"
        "---\n"
        "\n"
        "Body text with a `name:` mention that must not move.\n"
    )
    out = rewrite_name(text, "after")
    assert out == text.replace("name: before", "name: after")


def test_rewrite_name_preserves_crlf_line_endings():
    text = "---\r\nname: before\r\ndescription: d\r\n---\r\nbody\r\n"
    assert rewrite_name(
        text, "after"
    ) == "---\r\nname: before\r\ndescription: d\r\n---\r\nbody\r\n".replace(
        "name: before", "name: after"
    )


def test_rewrite_name_tolerates_spacing_before_the_colon():
    assert rewrite_name("---\nname : before\ndescription: d\n---\n", "after") == (
        "---\nname: after\ndescription: d\n---\n"
    )


def test_rewrite_name_ignores_an_indented_name_key():
    """An indented ``name:`` belongs to a nested mapping, not to the skill."""
    text = "---\ndescription: d\nmetadata:\n  name: nested\n---\nbody\n"
    assert rewrite_name(text, "after") is None


def test_rewrite_name_ignores_a_name_after_the_closing_delimiter():
    text = "---\ndescription: d\n---\nname: this is prose\n"
    assert rewrite_name(text, "after") is None


@pytest.mark.parametrize(
    "text",
    [
        "",
        "no frontmatter at all\n",
        "---\ndescription: d\n",  # block never closes
    ],
)
def test_rewrite_name_returns_none_when_there_is_nothing_to_rewrite(text):
    assert rewrite_name(text, "after") is None
