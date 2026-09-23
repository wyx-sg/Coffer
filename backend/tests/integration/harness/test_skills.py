"""Validate checked-in skills have the required frontmatter and resolve to a command name."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from .conftest import REPO_ROOT

SKILLS_DIR = REPO_ROOT / ".claude" / "skills"
# The checked-in skills are OpenSpec's, written by `openspec init --tools claude`
# and refreshed by `openspec update`.
EXPECTED = {
    "openspec-apply-change",
    "openspec-archive-change",
    "openspec-explore",
    "openspec-propose",
    "openspec-sync-specs",
    "openspec-update-change",
}


def _frontmatter(md: Path) -> dict:
    text = md.read_text()
    assert text.startswith("---\n"), f"{md} missing frontmatter"
    block = text.split("---\n", 2)[1]
    fm: dict[str, str] = {}
    for line in block.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_skill_has_required_frontmatter(name: str) -> None:
    md = SKILLS_DIR / name / "SKILL.md"
    assert md.exists(), f"missing skill {name}"
    fm = _frontmatter(md)
    assert fm.get("name") == name, "skill `name` must equal its directory name"
    assert fm.get("description"), "skill needs a description"


def test_no_unexpected_skills() -> None:
    # What git tracks, not what is on disk: a developer's own untracked skill
    # under .claude/skills/ is theirs, not the repo's.
    tracked = subprocess.run(
        ["git", "ls-files", "--", ".claude/skills/*/SKILL.md"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert {Path(p).parent.name for p in tracked} == EXPECTED
