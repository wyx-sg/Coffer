"""The hand-off the agent's Memory tab gives Claude Code: **Curate now** (spec
memory "Show each agent's own curation and ask it to curate now").
"""

from __future__ import annotations

from coffer.domain.handoff import Handoff, render_handoff
from coffer.infrastructure.memory.writers.claude_code import BLOCK_BEGIN, BLOCK_END, COPY_PREFIX


def claude_curation_prompt(folders: list[str]) -> str:
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
                f"Between {BLOCK_BEGIN} and {BLOCK_END} in each MEMORY.md is what my "
                "other agents learned, written by Coffer: Coffer rewrites it on every sync.",
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
                "Coffer's markers and what is between them as they are.",
                "Change nothing outside these folders. At the end, list each folder with "
                "how many memory files it had before and after.",
            ),
        )
    )


__all__ = ["claude_curation_prompt"]
