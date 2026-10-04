"""The prompts that hand a tidy of knowledge to the person's agent.

Coffer makes no model call over the corpus: judging what to merge, split, correct
or delete is the agent's work, following the "Tidying a collection" section of the
coffer-guide skill. The person starts it with **Tidy**, which pre-fills a
conversation with one of these prompts and sends it (spec knowledge "Hand a
tidy to the agent").
"""

from __future__ import annotations

from collections.abc import Sequence

from coffer.domain.handoff import Handoff, render_handoff
from coffer.domain.knowledge.entry import CollectionEntry

_STEPS = (
    'Read the "Tidying a collection" section of the coffer-guide skill first.',
    "When you finish, report what you merged, split, corrected, retired or deleted.",
)


def _count(n: int) -> str:
    return f"{n} document" + ("" if n == 1 else "s")


def collection_tidy_prompt(entry: CollectionEntry) -> str:
    """The prompt for tidying one collection."""
    return render_handoff(
        Handoff(
            task=(
                f"Tidy the knowledge collection `{entry.name}` by following the "
                '"Tidying a collection" section of the coffer-guide skill.'
            ),
            facts=(f"Path: {entry.folder_path}", f"Documents: {entry.document_count}"),
            steps=_STEPS,
        )
    )


def all_tidy_prompt(root: str, entries: Sequence[CollectionEntry]) -> str:
    """The prompt for tidying every collection, one at a time."""
    facts = [f"Knowledge root: {root}"]
    facts += [f"{e.name}: {e.folder_path} ({_count(e.document_count)})" for e in entries]
    return render_handoff(
        Handoff(
            task=(
                "Tidy every knowledge collection by following the "
                '"Tidying a collection" section of the coffer-guide skill, '
                "one collection at a time."
            ),
            facts=tuple(facts),
            steps=_STEPS,
        )
    )


__all__ = ["all_tidy_prompt", "collection_tidy_prompt"]
