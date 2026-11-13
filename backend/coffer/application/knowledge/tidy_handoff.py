"""The prompts that hand tidying knowledge to the person's agent.

Coffer makes no model call over the corpus: judging what to fold in, merge,
split, correct or delete is the agent's work, following the collection's own
rules file (ADR knowledge-collections-own-their-format).
The person starts it with **Tidy** or **Tidy all**, which pre-fills a
conversation with one of these prompts and sends it (spec knowledge "Hand a
tidy to the agent"). The prompt carries the collection's broken links,
so the agent fixes what Coffer found as well as what its rules ask, and it names
the two commands that make the tidy one change in the collection's change log
(spec knowledge "Record a tidy as one change").
"""

from __future__ import annotations

from collections.abc import Sequence

from coffer.domain.handoff import Handoff, render_handoff
from coffer.domain.knowledge.entry import CollectionEntry, Finding

_STEPS = (
    'Read the "Tidying a collection" section of the coffer-guide skill first.',
    "Before you change anything in a collection, run `coffer knowledge tidy-start <collection>`.",
    "Read the collection's rules file and tidy it by those rules; fix every broken link "
    "listed here.",
    "Leave alone anything you are not sure about — two files that disagree with "
    "no way to tell which is right, a large deletion, a change to the rules file — "
    "and list it in your report for the developer to decide.",
    "When you finish a collection, run `coffer knowledge tidy-finish <collection> "
    '--set summary="<your report>"`. The report says what you changed and what you '
    "left for the developer to decide, and ends with Gaps: questions the collection "
    "cannot answer and sources worth finding.",
)

#: How many findings a prompt lists before it says how many it left out.
MAX_FINDING_LINES = 40


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _counts(entry: CollectionEntry) -> str:
    return (
        f"{_plural(entry.note_count, 'Markdown file')}, "
        f"{_plural(entry.finding_count, 'broken link')}"
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
        return ["Broken links: none"]
    facts = [f"Broken links: {len(findings)}"]
    facts += [_finding_line(f) for f in findings[:MAX_FINDING_LINES]]
    if len(findings) > MAX_FINDING_LINES:
        facts.append(f"… and {len(findings) - MAX_FINDING_LINES} more")
    return facts


def collection_tidy_prompt(entry: CollectionEntry) -> str:
    """The prompt for tidying one collection."""
    return render_handoff(
        Handoff(
            task=(
                f"Tidy the knowledge collection `{entry.name}` by its own rules file, "
                'fixing the broken links Coffer found, as "Tidying a collection" in the '
                "coffer-guide skill says."
            ),
            facts=(
                f"Collection: {entry.name}",
                f"Path: {entry.folder_path}",
                f"Rules file: {entry.rules_file or 'none'}",
                f"Markdown files: {entry.note_count}",
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
                "Tidy every knowledge collection, one collection at a time, each by its "
                "own rules file, fixing the broken links `coffer knowledge check "
                '<collection>` lists, as "Tidying a collection" in the coffer-guide '
                "skill says."
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
