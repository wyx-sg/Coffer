"""Unit tests for ``SkillValidationError``'s message.

An import that failed with only ``skill folder invalid: skill_md_frontmatter_invalid``
sent the author hunting: the validator had the reason (a description one past the
standard's 1024-character cap) but the message dropped it. The message must carry
the reason the details already hold.
"""

from __future__ import annotations

from coffer.domain.errors import SkillValidationError


def test_frontmatter_errors_name_the_field_and_the_rule() -> None:
    err = SkillValidationError(
        "skill_md_frontmatter_invalid",
        {
            "errors": [
                {
                    "loc": ("description",),
                    "msg": "String should have at most 1024 characters",
                    "type": "string_too_long",
                }
            ]
        },
    )

    assert "skill_md_frontmatter_invalid" in str(err)
    assert "description: String should have at most 1024 characters" in str(err)


def test_several_frontmatter_errors_are_all_listed() -> None:
    err = SkillValidationError(
        "skill_md_frontmatter_invalid",
        {
            "errors": [
                {"loc": ("name",), "msg": "Field required"},
                {"loc": ("description",), "msg": "Field required"},
            ]
        },
    )

    assert "name: Field required" in str(err)
    assert "description: Field required" in str(err)


def test_path_detail_is_shown() -> None:
    err = SkillValidationError("skill_md_missing", {"path": "/tmp/x/SKILL.md"})

    assert str(err) == "skill folder invalid: skill_md_missing (/tmp/x/SKILL.md)"


def test_no_details_keeps_the_bare_reason() -> None:
    assert str(SkillValidationError("folder_missing")) == "skill folder invalid: folder_missing"
