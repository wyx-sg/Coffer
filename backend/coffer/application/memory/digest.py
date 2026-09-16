"""Rendering a partition's facts: one line per fact, for two readers.

This module owns what "one line per fact" looks like, and that one shape is
delivered to two different readers by two different callers:

* **``summary.md``**, written by ``organise.py`` from ``render_digest``
  below. Nothing in this codebase reads that file back, and that is not an
  oversight — its reader is the **person**, who browses a partition as a file
  tree with a preview beside it (spec memory FR-029). It is the human-facing
  half, and it is grouped and titled for someone skimming a folder.
* **L1 of the session-start context**, composed by ``context.py`` from
  ``fact_line`` below. FR-021 calls L1 "the partition's digest, one line per
  fact", and it means this module's line — not a second rendering of the
  same idea. ``context.py`` cannot reuse ``render_digest`` wholesale (it
  composes from a ``MemoryPort``, spends a token budget line by line, and
  interleaves two partitions), so it reuses the **line**, which is the part
  FR-021 actually names.

Keeping both on one renderer is what stops the two from drifting into two
slightly different ways of writing down the same fact — which is what they
had done.

Pure and synchronous — no filesystem, no model. That is the point of keeping
it a separate module from ``organise.py``: FR-019 requires a partition with
no internal connection configured to still get a **usable** digest, grouped
and readable, not a placeholder. Making the render itself incapable of I/O is
what guarantees that path is always taken, in tests and in an installation
with no model configured alike — there is no code path here that could
silently depend on a model having run first.

One line per fact, grouped by type, superseded facts omitted: a digest is
read by an agent at the start of a session, so it is a summary a person
skimming their teammate's notes would recognise, not a database dump.
"""

from __future__ import annotations

from collections.abc import Sequence

from coffer.domain.memory.fact import (
    STATUS_SUPERSEDED,
    TYPE_FEEDBACK,
    TYPE_PROJECT,
    TYPE_USER,
    Fact,
)

#: Group order: project facts first (what makes this partition distinct),
#: then the two personal types. Any type outside this tuple (a future
#: ``FACT_TYPES`` addition, or a hand-edited file with a stray value) is
#: still rendered — appended afterwards, sorted for determinism — rather
#: than silently dropped.
_TYPE_ORDER = (TYPE_PROJECT, TYPE_USER, TYPE_FEEDBACK)

_TYPE_LABELS = {
    TYPE_PROJECT: "Project",
    TYPE_USER: "About the developer",
    TYPE_FEEDBACK: "Feedback and standing instructions",
}


def recency(fact: Fact) -> str:
    """The latest timestamp attached to ``fact``, for a newest-first sort.

    Shared with ``context.py`` for the same reason ``fact_line`` is: the digest
    and the delivered lines are one concept, and two copies of "newest" drift
    exactly the way two copies of "one line per fact" did. ``context`` read
    only ``captured_at``, so a fact an agent timestamped only at the source
    scored ``""`` and sorted last there while sorting correctly in
    ``summary.md``.

    ISO-8601 strings sort lexically in chronological order. A fact with no
    timestamped origin at all (should not happen in practice, but a
    hand-edited file can manage it) sorts last rather than raising.
    """
    stamps = [o.captured_at or o.source_written_at for o in fact.origins]
    return max(stamps) if stamps else ""


def fact_line(fact: Fact) -> str:
    """One fact as one line — the shape both readers get (module docstring).

    Title, then the one-line description when there is one; never the body,
    which is what recall is for. A fact whose frontmatter lost its title
    falls back to its slug: facts are derived from an agent's own memory
    files, so a blank title is reachable, and naming *which* fact it is beats
    emphasising nothing.
    """
    title = fact.title.strip() or fact.slug
    description = fact.description.strip()
    if description:
        return f"- **{title}** — {description}"
    return f"- **{title}**"


def _type_order_key(type_: str) -> tuple[int, str]:
    if type_ in _TYPE_ORDER:
        return (_TYPE_ORDER.index(type_), "")
    return (len(_TYPE_ORDER), type_)


def render_digest(facts: Sequence[Fact], *, partition: str) -> str:
    """The ``summary.md`` body for one partition's ``facts``.

    Superseded facts are omitted entirely: they are still on disk (organise
    never deletes a fact, FR-018) but a digest is read for what is current,
    and a fact a later one replaced is exactly what "current" excludes.
    Within a type, newest first, by each fact's latest origin timestamp.
    """
    active = [f for f in facts if f.status != STATUS_SUPERSEDED]
    lines = [f"# {partition} — memory digest", ""]

    if not active:
        lines.append("No facts recorded yet.")
        return "\n".join(lines) + "\n"

    by_type: dict[str, list[Fact]] = {}
    for fact in active:
        by_type.setdefault(fact.type, []).append(fact)

    for type_ in sorted(by_type, key=_type_order_key):
        group = sorted(by_type[type_], key=recency, reverse=True)
        lines.append(f"## {_TYPE_LABELS.get(type_, type_)}")
        lines.extend(fact_line(f) for f in group)
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


__all__ = ["fact_line", "recency", "render_digest"]
