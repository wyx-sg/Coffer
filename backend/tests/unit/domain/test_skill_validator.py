"""AgentSkills validator covers SKILL.md, frontmatter, size, and symlink safety."""

from __future__ import annotations

import os
import textwrap

import pytest

from coffer.domain.skill.validator import (
    ValidationFailure,
    ValidationOk,
    validate_skill_folder,
)


def _write_skill(folder, *, name="my-skill", description="A test skill.", body="hello"):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        textwrap.dedent(
            f"""\
            ---
            name: {name}
            description: {description}
            ---

            {body}
            """
        ),
        encoding="utf-8",
    )


def test_happy_path(tmp_path):
    skill = tmp_path / "skill"
    _write_skill(skill)
    result = validate_skill_folder(skill)
    assert isinstance(result, ValidationOk)
    assert result.frontmatter.name == "my-skill"
    assert result.frontmatter.description == "A test skill."
    assert result.skill_md_sha256
    assert result.total_size_bytes > 0


def test_missing_folder(tmp_path):
    result = validate_skill_folder(tmp_path / "nope")
    assert isinstance(result, ValidationFailure)
    assert result.reason == "folder_missing"


def test_missing_skill_md(tmp_path):
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "README.md").write_text("not a SKILL.md")
    result = validate_skill_folder(skill)
    assert isinstance(result, ValidationFailure)
    assert result.reason == "skill_md_missing"


def test_no_frontmatter(tmp_path):
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("no frontmatter here")
    result = validate_skill_folder(skill)
    assert isinstance(result, ValidationFailure)
    assert result.reason == "skill_md_frontmatter_missing"


def test_empty_name(tmp_path):
    skill = tmp_path / "skill"
    _write_skill(skill, name="", description="x")
    result = validate_skill_folder(skill)
    assert isinstance(result, ValidationFailure)
    assert result.reason == "skill_md_frontmatter_invalid"


def test_invalid_name_pattern(tmp_path):
    skill = tmp_path / "skill"
    _write_skill(skill, name="UPPERCASE_NAME", description="x")
    result = validate_skill_folder(skill)
    assert isinstance(result, ValidationFailure)
    assert result.reason == "skill_md_frontmatter_invalid"


def test_name_too_long_is_clean_failure(tmp_path):
    """A 65-char name (>64) must be a clean ValidationFailure, not a 500 later.

    The master store enforces a 64-char folder-name cap and raises a bare
    ValueError; aligning the frontmatter cap to 64 turns this into a 422.
    """
    skill = tmp_path / "skill"
    _write_skill(skill, name="a" * 65, description="x")
    result = validate_skill_folder(skill)
    assert isinstance(result, ValidationFailure)
    assert result.reason == "skill_md_frontmatter_invalid"


def test_name_exactly_64_chars_is_ok(tmp_path):
    """The boundary value (64 chars) is still valid."""
    skill = tmp_path / "skill"
    _write_skill(skill, name="a" * 64, description="x")
    result = validate_skill_folder(skill)
    assert isinstance(result, ValidationOk)


def test_in_folder_symlink_size_counted_once(tmp_path):
    """A symlink to an in-folder file must not double-count the target's bytes."""
    skill = tmp_path / "skill"
    _write_skill(skill)
    payload = skill / "data.bin"
    payload.write_bytes(b"x" * 4096)
    # Symlink within the folder pointing at the real file. Following it during
    # the size walk would add 4096 a second time.
    os.symlink(payload, skill / "alias.bin")

    skill_md_bytes = (skill / "SKILL.md").stat().st_size
    result = validate_skill_folder(skill)
    assert isinstance(result, ValidationOk)
    # data.bin (4096) + SKILL.md only; the symlink contributes nothing.
    assert result.total_size_bytes == 4096 + skill_md_bytes


def test_path_escape_symlink_rejected(tmp_path):
    skill = tmp_path / "skill"
    _write_skill(skill)
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    os.symlink(outside, skill / "danger")
    result = validate_skill_folder(skill)
    assert isinstance(result, ValidationFailure)
    assert result.reason == "path_escape_symlinks"


def test_size_limit_exceeded(tmp_path):
    skill = tmp_path / "skill"
    _write_skill(skill)
    big = skill / "big.bin"
    big.write_bytes(b"x" * 2048)
    result = validate_skill_folder(skill, size_limit_bytes=1024)
    assert isinstance(result, ValidationFailure)
    assert result.reason == "size_limit_exceeded"


@pytest.mark.acceptance(
    spec="005-skill-manager", scenario="reject a skill with an over-long description"
)
def test_description_over_1024_chars_rejected(tmp_path):
    """agentskills.io caps `description` at 1024 chars; over-long is a clean 422."""
    skill = tmp_path / "skill"
    _write_skill(skill, description="d" * 1025)
    result = validate_skill_folder(skill)
    assert isinstance(result, ValidationFailure)
    assert result.reason == "skill_md_frontmatter_invalid"


@pytest.mark.acceptance(
    spec="005-skill-manager",
    scenario="recognize optional agentskills.io frontmatter fields",
)
def test_optional_frontmatter_fields_surfaced(tmp_path):
    """`license` and the experimental `allowed-tools` are parsed, not dropped."""
    skill = tmp_path / "skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        textwrap.dedent(
            """\
            ---
            name: my-skill
            description: A test skill.
            license: MIT
            allowed-tools:
              - Bash
              - Read
            ---

            body
            """
        ),
        encoding="utf-8",
    )
    result = validate_skill_folder(skill)
    assert isinstance(result, ValidationOk)
    assert result.frontmatter.license == "MIT"
    assert result.frontmatter.allowed_tools == ["Bash", "Read"]
