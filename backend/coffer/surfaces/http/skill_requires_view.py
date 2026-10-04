"""What a skill's SKILL.md says it needs, read from its master folder on each
request: the commands, the Coffer secrets, the MCP servers and custom-tool
groups (``requires:``), and the other skills it loads (``metadata.requires``).
Spec skill-manager "Show the commands a skill declares it needs", "Declare the
secrets a skill requires" and "Declare the tools a skill requires"."""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field

from coffer.application.skill.service import SkillService
from coffer.domain.resource import Resource
from coffer.domain.skill.binding import BindingState
from coffer.domain.skill.requirements import (
    required_skills_from_skill_md,
    requirements_from_skill_md,
)
from coffer.domain.skill.tool_state import resolve_tools
from coffer.surfaces.http.skill_dependencies import get_skill_secret_presence, get_skill_tool_states
from coffer.surfaces.http.skill_source_schemas import (
    SkillRequirementOut,
    SkillSecretRequirementOut,
    SkillSkillRequirementOut,
    SkillToolRequirementOut,
    requirement_out,
)


@dataclass
class RequiresView:
    commands: list[SkillRequirementOut] = field(default_factory=list)
    secrets: list[SkillSecretRequirementOut] = field(default_factory=list)
    tools: list[SkillToolRequirementOut] = field(default_factory=list)
    skills: list[SkillSkillRequirementOut] = field(default_factory=list)


def _live_agents(bindings: list[BindingState]) -> set[str]:
    return {b.agent_uid for b in bindings if b.enabled}


async def _skills_group(
    svc: SkillService,
    names: tuple[str, ...],
    mine: list[BindingState],
    agents_by_uid: dict[str, Resource],
    bindings_by_skill: dict[str, list[BindingState]] | None,
) -> list[SkillSkillRequirementOut]:
    library = {r.name: r for r in await svc.list_skills()}
    delivered = _live_agents(mine)
    out: list[SkillSkillRequirementOut] = []
    for name in names:
        other = library.get(name)
        if other is None:
            out.append(
                SkillSkillRequirementOut(
                    name=name,
                    uid=None,
                    found=False,
                    delivered_to_same_agents=False,
                    missing_agent_names=[],
                )
            )
            continue
        theirs = (
            bindings_by_skill.get(other.uid, [])
            if bindings_by_skill is not None
            else await svc.bindings_for(other.uid)
        )
        missing = sorted(delivered - _live_agents(theirs))
        out.append(
            SkillSkillRequirementOut(
                name=name,
                uid=other.uid,
                found=True,
                delivered_to_same_agents=not missing,
                missing_agent_names=[
                    agents_by_uid[u].name if u in agents_by_uid else u for u in missing
                ],
            )
        )
    return out


async def requires_view(
    svc: SkillService,
    skill: Resource,
    agents_by_uid: dict[str, Resource],
    bindings: list[BindingState],
    bindings_by_skill: dict[str, list[BindingState]] | None,
) -> RequiresView:
    try:
        text = (pathlib.Path(svc.master_path(skill.name)) / "SKILL.md").read_text("utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return RequiresView()
    parsed = requirements_from_skill_md(text)
    is_set = get_skill_secret_presence()
    view = RequiresView(
        commands=[requirement_out(q) for q in parsed.requirements],
        secrets=[
            SkillSecretRequirementOut(name=n, is_set=bool(is_set and is_set(n)))
            for n in parsed.secrets
        ],
    )
    states = get_skill_tool_states()
    if parsed.tools and states is not None:
        found, _unknown = resolve_tools(parsed.tools, await states.tool_states())
        view.tools = [
            SkillToolRequirementOut(
                name=t.state.name,
                uid=t.state.uid,
                kind=t.state.kind.value,
                status=t.state.status.value,
                why=t.requirement.why,
            )
            for t in found
        ]
    names = required_skills_from_skill_md(text)
    if names:
        view.skills = await _skills_group(svc, names, bindings, agents_by_uid, bindings_by_skill)
    return view
