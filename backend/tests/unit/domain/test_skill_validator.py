"""AgentSkills validator covers SKILL.md, frontmatter, size, and symlink safety."""

from __future__ import annotations

import os
import textwrap

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
