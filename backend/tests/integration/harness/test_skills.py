"""Validate checked-in skills have the required frontmatter and resolve to a command name."""

from __future__ import annotations

from pathlib import Path

import pytest

from .conftest import REPO_ROOT

SKILLS_DIR = REPO_ROOT / ".claude" / "skills"
EXPECTED = {"coffer-spec"}


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
