"""The hand-offs the memory pages give Claude Code: **Curate now** (spec
memory "Show each agent's own curation and ask it to curate now") and **Sort
into knowledge** (spec memory "Sort task material into knowledge on request").
"""

from __future__ import annotations

from coffer.domain.handoff import Handoff, render_handoff
from coffer.domain.memory.hub import HubEntry
from coffer.infrastructure.memory.writers.claude_code import BLOCK_BEGIN, BLOCK_END, COPY_PREFIX


def claude_curation_prompt(folders: list[str], rules: str) -> str:
    """The hand-off that asks Claude Code to curate its memory the way Auto
    Dream would, folder by folder, with the person watching."""
    listed = folders or ["(none yet: Coffer has written into no memory folder on this machine)"]
    return render_handoff(
        Handoff(
            task=(
                "Please consolidate your auto-memory folders below, the way your own "
                "background memory consolidation (Auto Dream) would."
            ),
            facts=(
                *(f"Memory folder: {folder}" for folder in listed),
                f"Between {BLOCK_BEGIN} and {BLOCK_END} in each MEMORY.md, and all of "
                f"{rules}, is what my other agents learned, written by Coffer: Coffer "
                "rewrites it on every sync.",
                f"A {COPY_PREFIX}*.md file left in a folder was copied in by an earlier "
                "Coffer; it is a memory like your own.",
            ),
            steps=(
                "Work one folder at a time: read its MEMORY.md and memory files, then tell "
                "me what you plan to merge, rewrite or delete before you change anything.",
                "Merge duplicates (one of your own memories that only repeats a line in "
                "Coffer's block can go), drop what is contradicted or stale, and turn "
                "relative dates into absolute ones.",
                "Keep the part of MEMORY.md outside Coffer's markers short, and leave "
                "Coffer's markers, what is between them and the rules file as they are.",
                "Change nothing outside these folders. At the end, list each folder with "
                "how many memory files it had before and after.",
            ),
        )
    )


def sort_prompt(waiting: list[tuple[HubEntry, str]], hub_root: str, more: int) -> str:
    """The hand-off that asks the person's agent to sort task material out of
    the memory hub into knowledge, a skill, memory or nothing (spec memory
    "Sort task material into knowledge on request")."""
    listed = [f"Memory {e.id}: {e.title or e.description} ({path})" for e, path in waiting]
    if more:
        listed.append(f"…and {more} more: `coffer memory to-sort` lists them all.")
    return render_handoff(
        Handoff(
            task=(
                "Please sort the memories below, which my agents filed as task notes, into "
                "where each belongs: my knowledge base, a skill, my memory, or nowhere."
            ),
            facts=(
                f"Each memory is a Markdown file in Coffer's memory hub, {hub_root}; read "
                "the files, never edit or delete them.",
                *listed,
                "Memory is about me: who I am, my preferences, how to work with me, a "
                "project's current state. Knowledge is about the world: how an outside "
                "system, team or process works, its pitfalls, anything that needs a source "
                "or goes stale. A skill is a fixed sequence of steps I repeat. A one-off "
                "request, or what a repository already says, belongs nowhere.",
                "`coffer knowledge list` names my collections; the coffer-guide skill says "
                "how to write pages and sources.",
            ),
            steps=(
                "First read every memory and show me a table: each memory, where you would "
                "put it (knowledge with the collection and page, skill, memory, or drop) and "
                "why. Change nothing until I agree.",
                "For knowledge: run `coffer knowledge tidy-start <collection>` first, write "
                "each note as a page or into the page that owns its subject, as the "
                "coffer-guide skill teaches, with `memory: <id>` in its `evidence` list, then "
                'run `coffer knowledge tidy-finish <collection> --set summary="<what you '
                'added>"`.',
                "For a skill: write a draft SKILL.md in a new folder and show it to me; "
                "import it with `coffer skill stage-folder` and `coffer skill stage-confirm` "
                "only if I agree.",
                "For memory or drop: write nothing; the drop list is mine to act on in the "
                "agent that wrote it.",
                "Record each memory you handled, so Coffer stops asking about it: "
                "`coffer memory sorted --set 'ids=[\"<id>\", ...]' --set outcome=<knowledge, "
                "skill, memory or drop> --set 'where=<collection/page, or the skill>'`.",
            ),
        )
    )


__all__ = ["claude_curation_prompt", "sort_prompt"]
