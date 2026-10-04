"""The prompt that hands one partition's tidying to the person's agent (spec memory
"Hand a partition's tidying to the agent").

Coffer runs no model over memory, so merging notes, splitting them, correcting or
retiring them is the agent's work. This writes the request from the facts Coffer
knows — the partition, its directory and how many notes it holds — and points at
the "Tidying memory" section of the ``coffer-guide`` skill, which holds the rules.
"""

from __future__ import annotations

from collections.abc import Sequence

from coffer.domain.handoff import Handoff, render_handoff
from coffer.infrastructure.memory import paths

_STEPS = (
    'Read the "Tidying memory" section of the coffer-guide skill before changing anything.',
    "When you are done, report what you merged, split, corrected, retired or deleted.",
)


def tidy_prompt(partition: str, *, note_count: int) -> str:
    """The text to copy, or to pre-fill a new conversation with."""
    return render_handoff(
        Handoff(
            task=(
                f"Tidy the memory partition `{partition}` by following the "
                '"Tidying memory" section of the coffer-guide skill.'
            ),
            facts=(
                f"Directory: {paths.partition_dir(partition)}",
                f"Notes: {note_count}",
            ),
            steps=_STEPS,
        )
    )


def tidy_all_prompt(partitions: Sequence[tuple[str, int]]) -> str:
    """The text that hands every partition's tidying to the agent, one partition at
    a time. ``partitions`` is ``(name, note_count)`` per partition."""
    facts = [f"Memory root: {paths.memory_root()}"]
    facts.extend(
        f"Partition `{name}`: {paths.notes_dir(name)} ({count} notes)" for name, count in partitions
    )
    return render_handoff(
        Handoff(
            task=(
                "Tidy every memory partition by following the "
                '"Tidying memory" section of the coffer-guide skill, one partition at a time.'
            ),
            facts=tuple(facts),
            steps=_STEPS,
        )
    )


__all__ = ["tidy_all_prompt", "tidy_prompt"]
