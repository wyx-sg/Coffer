"""Where a skill is found inside a folder, an archive or a repository (spec
skill-manager "Add skills from a Git repository")."""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.skill.discovery import MAX_DEPTH, find_skill_folders


def _skill(folder: pathlib.Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text("---\nname: x\ndescription: x\n---\n", encoding="utf-8")


def test_a_skill_at_the_root_is_the_only_one(tmp_path: pathlib.Path) -> None:
    _skill(tmp_path)
    _skill(tmp_path / "nested")
    assert find_skill_folders(tmp_path).folders == (".",)


@pytest.mark.acceptance(
    spec="skill-manager", scenario="a repository's skills are found below its top"
)
def test_collections_laid_out_like_the_public_repositories_are_found(
    tmp_path: pathlib.Path,
) -> None:
    # anthropics/skills: a template at the top level, the skills in skills/<name>/.
    _skill(tmp_path / "template")
    _skill(tmp_path / "skills" / "pdf")
    _skill(tmp_path / "skills" / "docx")
    # openai/skills: skills/.curated/<name>/ and skills/.system/<name>/.
    _skill(tmp_path / "skills" / ".curated" / "linear")
    _skill(tmp_path / "skills" / ".system" / "skill-installer")
    assert find_skill_folders(tmp_path).folders == (
        "skills/.curated/linear",
        "skills/.system/skill-installer",
        "skills/docx",
        "skills/pdf",
        "template",
    )


def test_a_skills_own_subfolders_are_part_of_it(tmp_path: pathlib.Path) -> None:
    _skill(tmp_path / "pack")
    _skill(tmp_path / "pack" / "examples" / "inner")
    assert find_skill_folders(tmp_path).folders == ("pack",)


def test_vcs_and_package_folders_and_deep_trees_are_skipped(tmp_path: pathlib.Path) -> None:
    _skill(tmp_path / ".git" / "x")
    _skill(tmp_path / "node_modules" / "y")
    deep = tmp_path
    for i in range(MAX_DEPTH + 1):
        deep = deep / f"d{i}"
    _skill(deep)
    assert find_skill_folders(tmp_path).folders == ()
