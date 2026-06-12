"""Pure function for assembling Coffer's built-in agent system prompt.

No I/O — takes only in-memory data. The result is passed verbatim to
``AgentAdapter.run_turn``.
"""

from __future__ import annotations

from dataclasses import dataclass

_COFFER_IDENTITY = """\
You are Coffer, a local-first AI assistant with access to the user's personal
knowledge vault. You can search memories, browse the knowledge base, run skills,
and invoke any other tools that have been connected to this Coffer instance.

Always be concise, helpful, and honest. Prefer structured output when listing
multiple items. Never reveal credential values or internal implementation details.
"""

_SKILL_CATALOGUE_HEADER = "\n## Available Skills\n"
_SKILL_CATALOGUE_NONE = "\n*(No skills have been added to this Coffer instance yet.)*\n"


@dataclass(frozen=True)
class SkillEntry:
    """Minimal skill descriptor used when building the system prompt."""

    name: str
    description: str


def build_system_prompt(skill_catalogue: list[SkillEntry]) -> str:
    """Assemble the system prompt for Coffer's built-in agent.

    Parameters
    ----------
    skill_catalogue:
        List of skill name/description pairs fetched from the gateway.
        An empty list results in a placeholder note instead of an empty table.

    Returns
    -------
    str
        The complete system prompt string ready to be sent to the LLM.
    """
    parts: list[str] = [_COFFER_IDENTITY, _SKILL_CATALOGUE_HEADER]
    if skill_catalogue:
        for entry in skill_catalogue:
            parts.append(f"- **{entry.name}**: {entry.description}\n")
    else:
        parts.append(_SKILL_CATALOGUE_NONE)
    return "".join(parts)
