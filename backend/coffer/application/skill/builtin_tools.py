"""Skill built-in MCP tools — registered into BuiltinToolRegistry at startup."""

from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING, Any

from coffer.application.builtin_tools import BuiltinTool, BuiltinToolRegistry
from coffer.domain.errors import ResourceNotFound

# NOTE: these imports are intentionally gated behind TYPE_CHECKING (type-hints only).
# SkillService (application/skill/service.py) currently imports
# coffer.infrastructure.skill.* directly — a pre-existing application→infrastructure
# layering violation from the spec-003/004 base code.  Importing it at runtime here
# would drag ORM/SQLAlchemy modules into the import graph of this module and every
# caller.  The TYPE_CHECKING guard is the surgical fix.
#
# DO NOT "simplify" this to a runtime import to match the pattern in
# application/memory/builtin_tools.py — that module's MemoryService does NOT have
# the same infrastructure coupling and is safe to import at runtime.
if TYPE_CHECKING:
    from coffer.application.resource_service import ResourceService
    from coffer.application.skill.service import SkillService


def register_skill_builtin_tools(
    registry: BuiltinToolRegistry,
    *,
    resources: ResourceService,
    skill_service: SkillService,
) -> None:
    """Wire the two skill tools into the gateway's built-in registry."""

    async def list_skills(_args: dict[str, Any]) -> dict[str, Any]:
        skills = await skill_service.list_skills()
        return {"skills": [{"name": s.name, "description": s.description or ""} for s in skills]}

    async def load_skill(args: dict[str, Any]) -> dict[str, Any]:
        raw_name = args.get("name")
        if not raw_name:
            return {"error": "load_skill requires a non-empty 'name' argument"}
        name = str(raw_name)
        try:
            skill = await skill_service.get_skill(name)
        except ResourceNotFound:
            return {"error": f"skill not found: {name!r}"}

        master_folder = pathlib.Path(skill_service.master_path(skill.name))
        skill_md = master_folder / "SKILL.md"
        if not skill_md.is_file():
            return {"error": f"SKILL.md missing for skill: {name!r}"}

        content = skill_md.read_text(encoding="utf-8")
        return {"name": skill.name, "content": content}

    registry.register(
        BuiltinTool(
            name="list_skills",
            description="List every skill registered in Coffer (name + description).",
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=list_skills,
        )
    )
    registry.register(
        BuiltinTool(
            name="load_skill",
            description="Load the full content (SKILL.md) of a skill by name.",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill name"},
                },
                "required": ["name"],
            },
            handler=load_skill,
        )
    )
