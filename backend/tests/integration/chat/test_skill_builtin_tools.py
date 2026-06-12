"""Integration tests for the skill built-in MCP tools.

Verifies that `register_skill_builtin_tools` registers `list_skills` and
`load_skill` into a real `BuiltinToolRegistry`, and that invoking them
returns the shapes expected by WU2's `_parse_skill_catalogue`.
"""

from __future__ import annotations

import pathlib
import textwrap
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.skill.builtin_tools import register_skill_builtin_tools
from coffer.domain.errors import ResourceNotFound
from coffer.domain.resource import Resource

# ---------------------------------------------------------------------------
# Fake helpers
# ---------------------------------------------------------------------------


def _make_resource(name: str, description: str) -> Resource:
    """Build a minimal Resource object for a skill."""
    now = datetime.now(tz=UTC)
    return Resource(
        id=1,
        kind="skill",
        name=name,
        description=description,
        config={},
        enabled=True,
        created_at=now,
        updated_at=now,
    )


def _make_skill_service(
    skills: list[Resource],
    *,
    tmp_path: pathlib.Path,
) -> Any:
    """Return a fake SkillService that reads SKILL.md files from tmp_path."""
    skills_by_name = {s.name: s for s in skills}

    # Write SKILL.md for each skill into tmp_path / <name> / SKILL.md
    for skill in skills:
        skill_folder = tmp_path / skill.name
        skill_folder.mkdir(parents=True, exist_ok=True)
        (skill_folder / "SKILL.md").write_text(
            textwrap.dedent(
                f"""\
                ---
                name: {skill.name}
                description: {skill.description}
                ---

                Body of {skill.name}.
                """
            ),
            encoding="utf-8",
        )

    svc = MagicMock()

    async def _list_skills() -> list[Resource]:
        return list(skills)

    async def _get_skill(name: str) -> Resource:
        if name not in skills_by_name:
            raise ResourceNotFound("skill", name)
        return skills_by_name[name]

    def _master_path(name: str) -> str:
        return str(tmp_path / name)

    svc.list_skills = _list_skills
    svc.get_skill = _get_skill
    svc.master_path = _master_path
    return svc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="008-agent-chat",
    scenario="skills are reachable as tools",
)
async def test_list_skills_returns_catalogue(tmp_path: pathlib.Path) -> None:
    """list_skills must return {"skills": [{"name": ..., "description": ...}]}."""
    skills = [
        _make_resource("format-python", "Formats Python code with black."),
        _make_resource("write-tests", "Writes pytest tests from a spec."),
    ]
    svc = _make_skill_service(skills, tmp_path=tmp_path)
    registry = BuiltinToolRegistry()
    register_skill_builtin_tools(registry, resources=MagicMock(), skill_service=svc)

    tool = registry.get("coffer__list_skills")
    assert tool is not None

    result = await tool.handler({})

    # Must match the shape _parse_skill_catalogue in WU2 expects.
    assert "skills" in result
    assert isinstance(result["skills"], list)
    assert len(result["skills"]) == 2

    names = {s["name"] for s in result["skills"]}
    descs = {s["description"] for s in result["skills"]}
    assert names == {"format-python", "write-tests"}
    assert "Formats Python code with black." in descs
    assert "Writes pytest tests from a spec." in descs

    # Every entry must have "name" and "description" keys.
    for entry in result["skills"]:
        assert set(entry.keys()) >= {"name", "description"}


async def test_list_skills_empty(tmp_path: pathlib.Path) -> None:
    """list_skills returns {"skills": []} when the vault has no skills."""
    svc = _make_skill_service([], tmp_path=tmp_path)
    registry = BuiltinToolRegistry()
    register_skill_builtin_tools(registry, resources=MagicMock(), skill_service=svc)

    tool = registry.get("coffer__list_skills")
    assert tool is not None

    result = await tool.handler({})
    assert result == {"skills": []}


async def test_load_skill_returns_content(tmp_path: pathlib.Path) -> None:
    """load_skill returns {"name": ..., "content": ...} with the SKILL.md text."""
    skills = [_make_resource("format-python", "Formats Python code.")]
    svc = _make_skill_service(skills, tmp_path=tmp_path)
    registry = BuiltinToolRegistry()
    register_skill_builtin_tools(registry, resources=MagicMock(), skill_service=svc)

    tool = registry.get("coffer__load_skill")
    assert tool is not None

    result = await tool.handler({"name": "format-python"})

    assert "name" in result
    assert "content" in result
    assert result["name"] == "format-python"
    assert "format-python" in result["content"]
    assert "Body of format-python" in result["content"]
    # No error key when skill exists.
    assert "error" not in result


async def test_load_skill_missing_returns_error(tmp_path: pathlib.Path) -> None:
    """load_skill returns a clear error payload instead of raising."""
    svc = _make_skill_service([], tmp_path=tmp_path)
    registry = BuiltinToolRegistry()
    register_skill_builtin_tools(registry, resources=MagicMock(), skill_service=svc)

    tool = registry.get("coffer__load_skill")
    assert tool is not None

    result = await tool.handler({"name": "does-not-exist"})

    assert "error" in result
    assert "does-not-exist" in result["error"]
    # Must not raise; "name" / "content" should not be present.
    assert "content" not in result


async def test_load_skill_skill_md_missing_returns_error(tmp_path: pathlib.Path) -> None:
    """Skill exists in the service but has no SKILL.md on disk → error payload."""
    skill = _make_resource("no-md-skill", "A skill whose SKILL.md was never written.")
    # Register in the service but do NOT create SKILL.md on disk.
    svc = MagicMock()

    async def _list_skills() -> list[Resource]:
        return [skill]

    async def _get_skill(name: str) -> Resource:
        if name == skill.name:
            return skill
        raise ResourceNotFound("skill", name)

    def _master_path(name: str) -> str:
        # Points at a directory that exists but contains no SKILL.md.
        folder = tmp_path / name
        folder.mkdir(parents=True, exist_ok=True)
        return str(folder)

    svc.list_skills = _list_skills
    svc.get_skill = _get_skill
    svc.master_path = _master_path

    registry = BuiltinToolRegistry()
    register_skill_builtin_tools(registry, resources=MagicMock(), skill_service=svc)

    tool = registry.get("coffer__load_skill")
    assert tool is not None

    result = await tool.handler({"name": "no-md-skill"})

    assert "error" in result
    assert "SKILL.md" in result["error"]
    assert "no-md-skill" in result["error"]
    assert "content" not in result


async def test_load_skill_missing_name_arg_returns_error(tmp_path: pathlib.Path) -> None:
    """load_skill called without a 'name' key must return an error, not raise KeyError."""
    svc = _make_skill_service([], tmp_path=tmp_path)
    registry = BuiltinToolRegistry()
    register_skill_builtin_tools(registry, resources=MagicMock(), skill_service=svc)

    tool = registry.get("coffer__load_skill")
    assert tool is not None

    # Simulate a malformed call with no 'name' key.
    result = await tool.handler({})

    assert "error" in result
    assert "name" in result["error"]
    assert "content" not in result


async def test_tool_names_registered_correctly(tmp_path: pathlib.Path) -> None:
    """Both tools must be accessible via the coffer__ prefix."""
    svc = _make_skill_service([], tmp_path=tmp_path)
    registry = BuiltinToolRegistry()
    register_skill_builtin_tools(registry, resources=MagicMock(), skill_service=svc)

    assert registry.get("coffer__list_skills") is not None
    assert registry.get("coffer__load_skill") is not None
    # Unprefixed access should return None (gateway contract).
    assert registry.get("list_skills") is None
    assert registry.get("load_skill") is None

    # Bare tool names must be stored unprefixed (registry length = 2 tools).
    assert len(registry) == 2
