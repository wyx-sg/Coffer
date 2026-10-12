"""The prompts that hand tidying knowledge to the person's agent.

Coffer makes no model call over the corpus: judging what to fold in, merge,
split, correct or delete is the agent's work, following the coffer-guide skill.
The person starts it with **Tidy** or **Tidy all**, which pre-fills a
conversation with one of these prompts and sends it (spec knowledge "Hand a
tidy to the agent"). The prompt carries the collection's mechanical findings,
so the agent fixes what Coffer found as well as what it judges, and it names
the two commands that make the tidy one change in the collection's change log
(spec knowledge "Record a tidy as one change").
"""

from __future__ import annotations

from collections.abc import Sequence

from coffer.domain.handoff import Handoff, render_handoff
from coffer.domain.knowledge.entry import CollectionEntry, Finding

_STEPS = (
    'Read the "Integrating sources" and "Tidying a collection" sections of the '
    "coffer-guide skill first.",
    "Before you change anything in a collection, run `coffer knowledge tidy-start <collection>`.",
    "Integrate every waiting source, then fix the mechanical findings, then merge, "
    "split and correct the pages.",
    "Leave alone anything you are not sure about — two pages that disagree with "
    "no way to tell which is right, a large deletion, a change to the README's "
    "page types — and list it in your report for the developer to decide.",
    "When you finish a collection, run `coffer knowledge tidy-finish <collection> "
    '--set summary="<your report>"`. The report says which sources you '
    "integrated or skipped, what you merged, split, corrected and deleted, and "
    "what you left for the developer to decide.",
)

#: How many findings a prompt lists before it says how many it left out.
MAX_FINDING_LINES = 40


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _counts(entry: CollectionEntry) -> str:
    return (
        f"{_plural(entry.page_count, 'page')}, "
        f"{_plural(entry.waiting_source_count, 'waiting source')}, "
        f"{_plural(entry.finding_count, 'finding')}"
    )


def _finding_line(finding: Finding) -> str:
    line = f"{finding.kind}: {finding.path}"
    if finding.target:
        line += f" → {finding.target}"
    if finding.others:
        line += f" (also {', '.join(finding.others)})"
    return line


def _finding_facts(findings: Sequence[Finding]) -> list[str]:
    if not findings:
        return ["Mechanical findings: none"]
    facts = [f"Mechanical findings: {len(findings)}"]
    facts += [_finding_line(f) for f in findings[:MAX_FINDING_LINES]]
    if len(findings) > MAX_FINDING_LINES:
        facts.append(f"… and {len(findings) - MAX_FINDING_LINES} more")
    return facts


def collection_tidy_prompt(entry: CollectionEntry) -> str:
    """The prompt for tidying one collection."""
    return render_handoff(
        Handoff(
            task=(
                f"Tidy the knowledge collection `{entry.name}`: integrate its waiting "
                'sources by the "Integrating sources" section of the coffer-guide skill, '
                'fix what Coffer found, then tidy its pages by "Tidying a collection".'
            ),
            facts=(
                f"Collection: {entry.name}",
                f"Path: {entry.folder_path}",
                f"Pages: {entry.page_count}",
                f"Waiting sources: {entry.waiting_source_count}",
                *_finding_facts(entry.findings),
            ),
            steps=_STEPS,
        )
    )


def all_tidy_prompt(root: str, entries: Sequence[CollectionEntry]) -> str:
    """The prompt for tidying every collection, one at a time. It carries each
    collection's counts; the agent reads a collection's findings with
    ``coffer knowledge check <collection>``."""
    facts = [f"Knowledge root: {root}"]
    facts += [f"{e.name}: {e.folder_path} ({_counts(e)})" for e in entries]
    return render_handoff(
        Handoff(
            task=(
                "Tidy every knowledge collection, one collection at a time: integrate "
                'its waiting sources by the "Integrating sources" section of the '
                "coffer-guide skill, fix what `coffer knowledge check <collection>` "
                'finds, then tidy its pages by "Tidying a collection".'
            ),
            facts=tuple(facts),
            steps=_STEPS,
        )
    )


__all__ = [
    "MAX_FINDING_LINES",
    "all_tidy_prompt",
    "collection_tidy_prompt",
]
