"""Rendering a partition's facts into the ``summary.md`` delivery reads.

Pure and synchronous — no filesystem, no model. That is the point of keeping
it a separate module from ``organise.py``: FR-032 requires a partition with
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


def _recency(fact: Fact) -> str:
    """The latest timestamp attached to ``fact``, for a newest-first sort.

    ISO-8601 strings sort lexically in chronological order. A fact with no
    timestamped origin at all (should not happen in practice, but a
    hand-edited file can manage it) sorts last rather than raising.
    """
    stamps = [o.captured_at or o.source_written_at for o in fact.origins]
    return max(stamps) if stamps else ""


def _line(fact: Fact) -> str:
    description = fact.description.strip()
    if description:
        return f"- **{fact.title}** — {description}"
    return f"- **{fact.title}**"


def _type_order_key(type_: str) -> tuple[int, str]:
    if type_ in _TYPE_ORDER:
        return (_TYPE_ORDER.index(type_), "")
    return (len(_TYPE_ORDER), type_)


def render_digest(facts: Sequence[Fact], *, partition: str) -> str:
    """The ``summary.md`` body for one partition's ``facts``.

    Superseded facts are omitted entirely: they are still on disk (organise
    never deletes a fact, FR-031) but a digest is read for what is current,
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
        group = sorted(by_type[type_], key=_recency, reverse=True)
        lines.append(f"## {_TYPE_LABELS.get(type_, type_)}")
        lines.extend(_line(f) for f in group)
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


__all__ = ["render_digest"]
