"""The hand-off that asks an agent to review skills and suggest changes.

Spec skill-manager "Hand a skill's review to an agent". Everything in it is a
suggestion the person may decline; Coffer never requires a skill to change.
Coffer does not judge what a skill needs (that is reading its body, scripts and
sub-skills); it hands the review to the person's agent with what a declaration
may hold and the facts of each skill: its master folder (the only place to
edit), whether it has declared anything, and where it came from. The prompt is
built when the person presses the button, from the folder as it is now.
"""

from __future__ import annotations

import pathlib
from collections.abc import Sequence
from dataclasses import dataclass

from coffer.domain.handoff import Handoff, render_handoff
from coffer.domain.skill.git_url import display_url
from coffer.domain.skill.requirements import requirements_from_skill_md
from coffer.domain.skill.source import (
    ArchiveImportSource,
    BuiltinSource,
    GitImportSource,
    LocalImportSource,
)

SkillSource = LocalImportSource | ArchiveImportSource | GitImportSource | BuiltinSource


@dataclass(frozen=True)
class ConformanceSkill:
    """What the prompt says about one skill."""

    name: str
    master: pathlib.Path
    #: SKILL.md or a profile wrote a ``requires:`` key.
    declared: bool
    source: SkillSource


_STEPS = (
    "Read the coffer-guide skill for Coffer's rules, then read each skill's whole folder "
    "(SKILL.md body, sub-skills and scripts) before suggesting anything.",
    "Everything here is a suggestion I can decline. First review and propose: say what you "
    "would change and why, ask me which suggestions to apply, and edit only what I agree to.",
    "The only thing Coffer reads is the `requires:` declaration, so Coffer can show what a "
    "skill needs. If you suggest one, put it under a top-level `requires:` in SKILL.md's "
    "frontmatter, listing only what the skill itself uses: the commands it runs "
    "(`command`, with `min_version`, `login_check` — a subcommand of the same command that "
    "exits 0 when logged in — `login` and `why` where they help), the Coffer secrets it "
    "uses, by id (`coffer secret list --json` lists them), and the MCP servers and tool "
    "groups it calls, by their Coffer name.",
    "Do not declare on behalf of another skill it delegates to, Coffer-managed or external; "
    "that skill declares its own. Keep `metadata.requires` for the skills it loads. If a "
    "skill truly needs nothing, `requires: []` tells Coffer it declared nothing rather "
    "than never declared.",
    "Compare each skill's `description` with the other skills in my library (the other "
    "folders beside its master folder): where two would be picked for the same request, "
    "say which, and suggest wording that tells them apart.",
    "If a skill is meant to be run only when I ask for it, or only by another skill, "
    "suggest declaring that: `disable-model-invocation: true` in SKILL.md's frontmatter "
    "for Claude Code, and `policy: {allow_implicit_invocation: false}` in "
    "`agents/openai.yaml` for Codex. Say that the agent then no longer picks it on its own, "
    "and that a skill which calls it by name still can in Codex but not in Claude Code, "
    "so a skill other skills rely on should keep the default.",
    "Do not restructure a skill, add a profiles folder, or rename or move files for any "
    "library convention; mention such patterns only if I ask.",
    "If a skill holds a secret's value or my own identity (name, email, account) in a file, "
    "you may point it out and suggest Coffer's secret store (`coffer secret set --name`, "
    "`coffer run --secret`) or deriving it at run time (e.g. `git config user.email`); if I "
    "prefer to keep it as it is, leave it.",
    "Edit files in each master folder only, commit nothing, and show me the diff of each "
    "master folder when you finish.",
)


def read_declared(master: pathlib.Path) -> bool:
    """Whether the folder's SKILL.md writes ``requires:``; false for a folder
    that cannot be read."""
    try:
        text = (master / "SKILL.md").read_text("utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return requirements_from_skill_md(text).declared


def _source_fact(source: SkillSource) -> str:
    if isinstance(source, GitImportSource):
        folder = source.subpath or "the repository's top folder"
        return (
            f"Source: Git repository {display_url(source.url)}, folder {folder}, pinned to "
            f"{source.commit[:7]}. Edits to the master folder are recorded as local edits "
            "against the pinned commit and are kept across updates; also suggest the change "
            "for the upstream repository."
        )
    if isinstance(source, BuiltinSource):
        return (
            "Source: Coffer's own skill. Its folder is rewritten from the running build, so "
            "do not edit it; report what you find."
        )
    if isinstance(source, ArchiveImportSource):
        return f"Source: imported from the archive {source.archive_name}."
    return f"Source: imported from the folder {source.original_path}."


def _facts(skill: ConformanceSkill, many: bool) -> list[str]:
    declaration = (
        "present — review it"
        if skill.declared
        else "none yet — its SKILL.md has no `requires:` key"
    )
    lines = [
        f"Master folder (edit here, and only here): {skill.master}",
        f"Declaration: {declaration}",
        _source_fact(skill.source),
    ]
    if not many:
        return [f"Skill: {skill.name}", *lines]
    return [f"{skill.name} — {line[0].lower()}{line[1:]}" for line in lines]


def conformance_prompt(skills: Sequence[ConformanceSkill]) -> str:
    """The prompt that asks an agent to check ``skills`` and fix what it finds."""
    many = len(skills) > 1
    task = (
        f"Review these {len(skills)} skills and suggest how they could declare what they need, "
        "so Coffer can show it. Where a skill declares nothing, suggest a declaration."
        if many
        else f"Review skill {skills[0].name} and suggest how it could declare what it needs, "
        "so Coffer can show it. If it declares nothing, suggest a declaration."
    )
    facts: list[str] = []
    for skill in skills:
        facts.extend(_facts(skill, many))
    return render_handoff(Handoff(task=task, facts=tuple(facts), steps=_STEPS))


__all__ = ["ConformanceSkill", "SkillSource", "conformance_prompt", "read_declared"]
