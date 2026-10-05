"""The prompt that hands a review of skills to an agent (spec skill-manager
"Hand a skill's review to an agent")."""

from __future__ import annotations

import pathlib

import pytest

from coffer.application.skill.conformance_handoff import (
    ConformanceSkill,
    conformance_prompt,
    read_declared,
)
from coffer.domain.skill.source import BuiltinSource, GitImportSource, LocalImportSource

_GIT = GitImportSource(
    url="https://example.com/o/r.git",
    commit="abcdef1234567",
    content_hash="h",
    ref=None,
    subpath="skills/a",
)


def _skill(name: str, declared: bool, source: object = None) -> ConformanceSkill:
    return ConformanceSkill(
        name,
        pathlib.Path(f"/m/{name}"),
        declared,
        source or LocalImportSource(original_path="/p"),  # type: ignore[arg-type]
    )


@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="the review prompt names each skill's folder, declaration and source",
)
def test_the_prompt_names_each_skills_folder_declaration_and_source() -> None:
    prompt = conformance_prompt([_skill("a", False, _GIT), _skill("b", True)])
    assert "/m/a" in prompt and "/m/b" in prompt
    assert "a — declaration: none yet" in prompt
    assert "b — declaration: present" in prompt
    assert "recorded as local edits against the pinned commit and are kept across updates" in prompt
    assert "abcdef1" in prompt and "example.com/o/r.git" in prompt
    assert "imported from the folder /p" in prompt


@pytest.mark.acceptance(
    spec="skill-manager", scenario="the review prompt offers suggestions and restructures nothing"
)
def test_the_prompt_proposes_first_and_restructures_nothing() -> None:
    prompt = conformance_prompt([_skill("a", False)])
    assert "suggestion I can decline" in prompt
    assert "ask me which suggestions to apply" in prompt
    assert "Do not restructure a skill, add a profiles folder" in prompt
    assert "if I prefer to keep it as it is, leave it" in prompt
    assert "commit nothing" in prompt
    assert "coffer-guide" in prompt and "`requires: []`" in prompt
    assert "install" not in prompt.lower()


def test_a_builtin_skill_is_not_to_be_edited() -> None:
    assert "do not edit it" in conformance_prompt([_skill("coffer-guide", True, BuiltinSource())])


def test_read_declared_reads_skill_md_and_profiles(tmp_path: pathlib.Path) -> None:
    assert read_declared(tmp_path) is False
    (tmp_path / "SKILL.md").write_text("---\nname: s\n---\n")
    assert read_declared(tmp_path) is False
    (tmp_path / "profiles").mkdir()
    (tmp_path / "profiles" / "p.md").write_text("---\nrequires: []\n---\n")
    assert read_declared(tmp_path) is True
