"""The union of a skill's ``requires:`` across SKILL.md and its profile files.

A skill library keeps per-environment values in ``profiles/<name>.md``; a
profile's frontmatter may carry its own ``requires:``. An agent picks one
profile at run time, which Coffer cannot know, so every profile counts and
each requirement records which profiles declared it. Spec skill-manager
"Read the requirements profile files declare".
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from coffer.domain.skill.requirements import (
    CommandRequirement,
    RequirementsParse,
    ToolRequirement,
    requirements_from_skill_md,
)


def requirements_of_skill(skill_md: str, profiles: Sequence[tuple[str, str]]) -> RequirementsParse:
    """What a skill needs: the union of SKILL.md's ``requires:`` and that of
    every profile file's frontmatter (``profiles`` is ``(name, text)`` pairs).

    An agent picks one profile at run time, which Coffer cannot know, so every
    profile counts. Each requirement says which profiles declared it; a command
    several sources declare is one requirement (highest minimum, first
    non-empty text, profiles joined). Spec skill-manager "Read the requirements
    profile files declare".
    """
    sources: list[tuple[str | None, RequirementsParse]] = [
        (None, requirements_from_skill_md(skill_md))
    ]
    sources += [(name, requirements_from_skill_md(text)) for name, text in profiles]
    commands: dict[str, CommandRequirement] = {}
    secrets: dict[str, tuple[str, ...]] = {}
    tools: dict[str, ToolRequirement] = {}
    warnings: list[str] = []
    for source, parsed in sources:
        tag = (source,) if source is not None else ()
        warnings.extend(
            w if source is None else f"profiles/{source}.md: {w}" for w in parsed.warnings
        )
        for req in parsed.requirements:
            have = commands.get(req.command)
            commands[req.command] = (
                replace(req, profiles=tag) if have is None else _merge_command(have, req, tag)
            )
        for name in parsed.secrets:
            secrets[name] = _join(secrets[name], tag) if name in secrets else tag
        for tool in parsed.tools:
            have_tool = tools.get(tool.name)
            tools[tool.name] = (
                replace(tool, profiles=tag)
                if have_tool is None
                else ToolRequirement(
                    tool.name, have_tool.why or tool.why, _join(have_tool.profiles, tag)
                )
            )
    return RequirementsParse(
        tuple(commands.values()), tuple(secrets), tuple(tools.values()), tuple(warnings), secrets
    )


def _join(have: tuple[str, ...], more: tuple[str, ...]) -> tuple[str, ...]:
    # SKILL.md is read first and is the only source with an empty tag, so an
    # entry that already has no profiles was declared by SKILL.md itself: it
    # stays unconditional whatever a profile adds.
    if not have:
        return ()
    return tuple(dict.fromkeys([*have, *more]))


def _merge_command(
    have: CommandRequirement, req: CommandRequirement, tag: tuple[str, ...]
) -> CommandRequirement:
    versions = [v for v in (have.min_version, req.min_version) if v]
    best = None
    for v in versions:
        if best is None or _version_key(v) > _version_key(best):
            best = v
    return CommandRequirement(
        command=have.command,
        title=have.title or req.title,
        min_version=best,
        login_check=have.login_check or req.login_check,
        login=have.login or req.login,
        why=have.why or req.why,
        profiles=_join(have.profiles, tag),
    )


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split("."))


__all__ = ["requirements_of_skill"]
