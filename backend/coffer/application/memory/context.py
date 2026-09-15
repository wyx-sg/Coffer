"""Composing the session-start context: L0 always, L1 when it fits (spec
memory FR-050, FR-051).

Delivery has exactly three layers (FR-050): **L0**, always — who the
developer is, what this project's memory holds, and how to ask for more;
**L1**, when the budget allows it — the current project partition's digest,
one line per fact; **L2** — ``coffer__recall`` (``recall.py``), on request,
never composed here. This module builds L0 and L1 and nothing else.

Three things this module is deliberately narrow about:

* **It never resolves an agent's scope or a cwd's partition from scratch.**
  ``MemoryPort`` below is the narrow slice of ``MemoryService`` this needs —
  visible partitions, a partition's facts, the partition list — so a unit
  test can fake it with no database at all, and the production composition
  root hands in the real service unchanged (structural typing: the Protocol
  is not a base class ``MemoryService`` has to inherit from).
* **It reads the facts as aggregation and organise left them.** There is no
  second judgement applied on top any more: the developer's hide/pin/
  supersede/settle overrides are gone with the surface that recorded them, so
  what a fact's own frontmatter says is what delivery says.
* **The budget is spent in FR-051's stated preference order**: ``global``'s
  personal facts, then the current project's most recent — by filling L0 (the
  global side of that order) completely before L1 ever gets a look at what is
  left. A tiny budget can therefore ship L0 alone with L1 entirely absent; it
  can never ship a half of L0.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from coffer.application.memory.service import PartitionSummary
from coffer.domain.memory.budget import estimate_tokens
from coffer.domain.memory.fact import Fact
from coffer.domain.memory.partition import GLOBAL_PARTITION

#: "A few hundred tokens" for L0 (spec memory User Story 3), with headroom
#: left over for L1 when the current project's digest is small enough to
#: fit alongside it. Approximate by design (see ``domain.memory.budget``) —
#: this is a ceiling to stay well clear of, not a number to hit exactly.
DEFAULT_BUDGET_TOKENS = 600

#: Tokens reserved, unconditionally, for the closing line that names how
#: many facts were left out and how to reach the rest (FR-051). Reserved
#: before any fact line is considered, so trimming can never crowd out the
#: one line the budget rule exists to guarantee. Generous relative to a
#: realistic pointer sentence — see ``_pointer`` — on the same "approximate
#: is fine, silently missing is not" principle as the estimator itself.
_POINTER_RESERVE_TOKENS = 40

LAYER_L0 = "L0"
LAYER_L1 = "L1"


class MemoryPort(Protocol):
    """The slice of ``MemoryService`` composing a context needs: scope and
    reads, never aggregation. Matches ``MemoryService``'s real signatures
    structurally, so the production service satisfies it with no adapter."""

    async def visible_partitions(self, agent: str | None) -> Sequence[str]: ...

    async def list_facts(self, partition: str, *, agent: str | None = None) -> Sequence[Fact]: ...

    async def list_partitions(self) -> Sequence[PartitionSummary]: ...


@dataclass(frozen=True)
class ComposedContext:
    """What ``compose_context`` hands back: the text, which partition it
    resolved ``cwd`` to, and enough accounting for a caller — or a test — to
    confirm the budget rule actually held (FR-051)."""

    text: str
    partition: str
    facts_included: int
    facts_omitted: int
    #: Which of L0/L1 actually made it in. L0 is always present; L1 only
    #: when at least one project-partition fact line fit the budget.
    layers: tuple[str, ...]


def _recency(fact: Fact) -> str:
    """The latest origin timestamp a fact carries, or ``""`` for none.

    ISO-8601 strings sort lexicographically the same as chronologically, so
    this doubles as a sort key with no parsing.
    """
    return max((origin.captured_at for origin in fact.origins), default="")


def _ordered(facts: Iterable[Fact]) -> tuple[Fact, ...]:
    """Most recent first — the whole of FR-051's within-partition order now
    that pinning is gone."""
    return tuple(sorted(facts, key=_recency, reverse=True))


def _fact_line(fact: Fact) -> str:
    title = fact.title.strip() or fact.slug
    description = fact.description.strip()
    return f"- {title}: {description}" if description else f"- {title}"


def _pointer(omitted: int) -> str:
    if omitted:
        return (
            f"{omitted} more fact(s) not shown here — call coffer__recall with a "
            "natural-language query to find them."
        )
    return "Call coffer__recall with a natural-language query for anything more specific."


def _resolve_cwd_partition(partitions: Sequence[PartitionSummary], cwd: str) -> str:
    """Map ``cwd`` to its project partition the way aggregation named it:
    by the absolute ``project_root`` recorded on the partition's own
    Resource (``MemoryPartitionConfig.project_root``), never recomputed.

    The longest matching root wins, so a project nested inside another
    checked-out repository resolves to the inner one. An unknown, blank or
    unresolvable ``cwd`` — including one under no registered project root —
    yields ``global``, which FR's own wording treats as a normal answer, not
    an error.
    """
    stripped = (cwd or "").strip()
    if not stripped:
        return GLOBAL_PARTITION
    try:
        target = pathlib.Path(stripped).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return GLOBAL_PARTITION

    best_name: str | None = None
    best_depth = -1
    for summary in partitions:
        if summary.name == GLOBAL_PARTITION or not summary.project_root:
            continue
        try:
            root = pathlib.Path(summary.project_root).expanduser().resolve()
        except (OSError, RuntimeError, ValueError):
            continue
        if target != root and root not in target.parents:
            continue
        depth = len(root.parts)
        if depth > best_depth:
            best_depth = depth
            best_name = summary.name
    return best_name or GLOBAL_PARTITION


class _Budget:
    """Tracks remaining tokens, with the pointer's cost reserved up front."""

    def __init__(self, total_tokens: int) -> None:
        self._remaining = total_tokens - _POINTER_RESERVE_TOKENS

    def fits(self, line: str) -> bool:
        return estimate_tokens(line) <= self._remaining

    def spend(self, line: str) -> None:
        self._remaining -= estimate_tokens(line)


async def compose_context(
    memory: MemoryPort,
    *,
    agent: str | None,
    cwd: str,
    budget_tokens: int = DEFAULT_BUDGET_TOKENS,
) -> ComposedContext:
    """Build the session-start payload: L0 always, L1 when it fits."""
    visible = set(await memory.visible_partitions(agent))
    project_partition = _resolve_cwd_partition(await memory.list_partitions(), cwd)

    global_facts: Sequence[Fact] = ()
    if GLOBAL_PARTITION in visible:
        global_facts = await memory.list_facts(GLOBAL_PARTITION, agent=agent)
    project_facts: Sequence[Fact] = ()
    if project_partition != GLOBAL_PARTITION and project_partition in visible:
        project_facts = await memory.list_facts(project_partition, agent=agent)

    shown = {f.key: f for f in list(global_facts) + list(project_facts)}
    global_visible = _ordered(f for f in shown.values() if f.partition == GLOBAL_PARTITION)
    project_visible = (
        _ordered(f for f in shown.values() if f.partition == project_partition)
        if project_partition != GLOBAL_PARTITION
        else ()
    )

    budget = _Budget(budget_tokens)
    lines: list[str] = ["## Coffer memory"]
    budget.spend(lines[0])

    label = "Known about you:" if global_visible else "No facts on file about you yet."
    lines.append(label)
    budget.spend(label)

    global_included = 0
    for fact in global_visible:
        line = _fact_line(fact)
        if not budget.fits(line):
            break
        lines.append(line)
        budget.spend(line)
        global_included += 1

    if project_partition == GLOBAL_PARTITION:
        project_line = "No project-specific memory for this working directory."
    else:
        project_line = (
            f"Project '{project_partition}' holds {len(project_visible)} fact(s) in memory."
        )
    lines.append(project_line)
    budget.spend(project_line)

    layers = [LAYER_L0]
    project_included = 0
    if project_visible:
        label = f"Recent facts in '{project_partition}':"
        if budget.fits(label):
            budget.spend(label)
            l1_lines = [label]
            for fact in project_visible:
                line = _fact_line(fact)
                if not budget.fits(line):
                    break
                l1_lines.append(line)
                budget.spend(line)
                project_included += 1
            if project_included:
                lines.extend(l1_lines)
                layers.append(LAYER_L1)

    included = global_included + project_included
    total = len(global_visible) + len(project_visible)
    omitted = total - included
    lines.append(_pointer(omitted))

    return ComposedContext(
        text="\n".join(lines),
        partition=project_partition,
        facts_included=included,
        facts_omitted=omitted,
        layers=tuple(layers),
    )


__all__ = [
    "DEFAULT_BUDGET_TOKENS",
    "LAYER_L0",
    "LAYER_L1",
    "ComposedContext",
    "MemoryPort",
    "compose_context",
]
