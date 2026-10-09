"""The prompts that hand work on knowledge to the person's agent.

Coffer makes no model call over the corpus: judging what to fold in, merge,
split, correct or delete is the agent's work, following the coffer-guide skill.
The person starts it with **Tidy** or **Check with agent**, which pre-fills a
conversation with one of these prompts and sends it (spec knowledge "Hand a
tidy to the agent", "Hand a check to the agent").
"""

from __future__ import annotations

from collections.abc import Sequence

from coffer.domain.handoff import Handoff, render_handoff
from coffer.domain.knowledge.entry import CollectionEntry

_TIDY_STEPS = (
    'Read the "Integrating sources" and "Tidying a collection" sections of the '
    "coffer-guide skill first.",
    "Integrate every waiting source before tidying the pages.",
    "When you finish, report which sources you integrated or skipped, and what you "
    "merged, split, corrected, retired or deleted.",
)

_CHECK_STEPS = (
    'Read the "Checking a collection" section of the coffer-guide skill first.',
    "Change nothing: no file is written, moved or deleted.",
    "Report contradictions, stale statements, subjects covered twice and subjects "
    "that deserve a page of their own, each naming the pages involved, then the "
    "mechanical findings below with what you would do about each.",
)

#: How many findings a check prompt lists before it says how many it left out.
MAX_FINDING_LINES = 40


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _counts(entry: CollectionEntry) -> str:
    return (
        f"{_plural(entry.page_count, 'page')}, "
        f"{_plural(entry.waiting_source_count, 'waiting source')}"
    )


def collection_tidy_prompt(entry: CollectionEntry) -> str:
    """The prompt for tidying one collection."""
    return render_handoff(
        Handoff(
            task=(
                f"Tidy the knowledge collection `{entry.name}`: integrate its waiting "
                'sources by the "Integrating sources" section of the coffer-guide skill, '
                'then tidy its pages by "Tidying a collection".'
            ),
            facts=(
                f"Path: {entry.folder_path}",
                f"Pages: {entry.page_count}",
                f"Waiting sources: {entry.waiting_source_count}",
            ),
            steps=_TIDY_STEPS,
        )
    )


def all_tidy_prompt(root: str, entries: Sequence[CollectionEntry]) -> str:
    """The prompt for tidying every collection, one at a time."""
    facts = [f"Knowledge root: {root}"]
    facts += [f"{e.name}: {e.folder_path} ({_counts(e)})" for e in entries]
    return render_handoff(
        Handoff(
            task=(
                "Tidy every knowledge collection, one collection at a time: integrate "
                'its waiting sources by the "Integrating sources" section of the '
                'coffer-guide skill, then tidy its pages by "Tidying a collection".'
            ),
            facts=tuple(facts),
            steps=_TIDY_STEPS,
        )
    )


def _finding_line(kind: str, path: str, target: str | None, others: Sequence[str]) -> str:
    line = f"{kind}: {path}"
    if target:
        line += f" → {target}"
    if others:
        line += f" (also {', '.join(others)})"
    return line


def collection_check_prompt(entry: CollectionEntry) -> str:
    """The prompt for checking one collection; reports, changes nothing."""
    facts = [f"Path: {entry.folder_path}", f"Pages: {entry.page_count}"]
    findings = entry.findings
    if findings:
        facts.append(f"Mechanical findings: {len(findings)}")
        facts += [
            _finding_line(f.kind, f.path, f.target, f.others) for f in findings[:MAX_FINDING_LINES]
        ]
        if len(findings) > MAX_FINDING_LINES:
            facts.append(f"… and {len(findings) - MAX_FINDING_LINES} more")
    else:
        facts.append("Mechanical findings: none")
    return render_handoff(
        Handoff(
            task=(
                f"Check the knowledge collection `{entry.name}` by following the "
                '"Checking a collection" section of the coffer-guide skill, and report '
                "what you find without changing anything."
            ),
            facts=tuple(facts),
            steps=_CHECK_STEPS,
        )
    )


__all__ = [
    "MAX_FINDING_LINES",
    "all_tidy_prompt",
    "collection_check_prompt",
    "collection_tidy_prompt",
]
