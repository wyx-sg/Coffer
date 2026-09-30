"""A skill Git import on a machine with no ``git`` is a coded refusal carrying
the install hand-off, not an unhandled ``FileNotFoundError``."""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.skill_source_errors import SkillSourceUnreachable
from coffer.infrastructure.skill import git_source
from coffer.infrastructure.skill.git_source import GitSource

pytestmark = pytest.mark.anyio


@pytest.mark.acceptance(
    spec="skill-manager", scenario="a skill import with no git hands installing it to an agent"
)
async def test_a_missing_git_refuses_with_the_install_handoff(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(git_source, "machine_label", lambda: "macOS 15.6, arm64")
    source = GitSource(git=str(tmp_path / "no-such-git"))

    with pytest.raises(SkillSourceUnreachable) as refused:
        await source.clone("https://example.com/skills.git", tmp_path / "dest")

    assert refused.value.code == "SKILL_SOURCE_UNREACHABLE"
    assert str(refused.value) == "git is not installed on this machine"
    details = refused.value.error_details
    assert details["reason"] == "git_missing"
    prompt = details["handoff"]["prompt"]  # type: ignore[index]
    assert "This machine: macOS 15.6, arm64." in prompt
    assert "adding and updating skills from a Git repository" in prompt
    assert "`git --version`" in prompt
    assert "brew" not in prompt and "xcode-select" not in prompt


async def test_a_git_failure_carries_no_handoff(tmp_path: pathlib.Path) -> None:
    fake = tmp_path / "git"
    fake.write_text("#!/bin/sh\necho 'fatal: repository not found' >&2\nexit 128\n")
    fake.chmod(0o755)
    with pytest.raises(SkillSourceUnreachable) as refused:
        await GitSource(git=str(fake)).clone("https://example.com/x.git", tmp_path / "d")
    assert "repository not found" in str(refused.value)
    assert not hasattr(refused.value, "error_details")
