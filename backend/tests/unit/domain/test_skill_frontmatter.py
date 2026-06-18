"""Unit tests for the SKILL.md frontmatter model (agentskills.io alignment)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from coffer.domain.skill.frontmatter import _DESCRIPTION_MAX, SkillFrontmatter


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
