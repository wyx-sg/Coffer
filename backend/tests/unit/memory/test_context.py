"""Unit tests for composing the session-start context (application/memory/context.py).

The ``MemoryPort`` here is a plain in-memory fake — no database, no
filesystem — which is exactly what the narrow Protocol in ``context.py`` is
for. No env pinning is needed either: this module never touches
``$COFFER_MEMORY_ROOT`` at all.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest

from coffer.application.memory.context import (
    LAYER_L0,
    LAYER_L1,
    ComposedContext,
    compose_context,
)
from coffer.application.memory.digest import render_digest
from coffer.application.memory.service import PartitionSummary
from coffer.domain.memory.budget import estimate_tokens
from coffer.domain.memory.fact import TYPE_PROJECT, TYPE_USER, Fact, Origin
from coffer.domain.memory.partition import GLOBAL_PARTITION


def _fact(
    *,
    slug: str,
    partition: str,
    title: str | None = None,
    description: str = "A fact worth knowing.",
    body: str = "body",
    type_: str = TYPE_PROJECT,
    captured_at: str = "2024-01-01T00:00:00+00:00",
) -> Fact:
    return Fact(
        slug=slug,
        title=title or slug,
        description=description,
        type=type_,
        body=body,
        partition=partition,
        origins=(
            Origin(
                agent="claude_code",
                native_path=f"/native/{slug}.md",
                captured_at=captured_at,
            ),
        ),
    )


class FakeMemory:
    def __init__(
        self,
        *,
        visible: Sequence[str],
        facts: Mapping[str, Sequence[Fact]],
        partitions: Sequence[PartitionSummary] = (),
    ) -> None:
        self._visible = list(visible)
        self._facts = dict(facts)
        self._partitions = list(partitions)

    async def visible_partitions(self, agent: str | None) -> Sequence[str]:
        return self._visible

    async def list_facts(self, partition: str, *, agent: str | None = None) -> Sequence[Fact]:
        return self._facts.get(partition, ())

    async def list_partitions(self) -> Sequence[PartitionSummary]:
        return self._partitions


def _many_project_facts(n: int, *, partition: str = "myproj") -> list[Fact]:
    return [
        _fact(
            slug=f"fact-{i}",
            partition=partition,
            title=f"Fact number {i}",
            description="A long-ish description so many of these do not fit a small budget.",
            captured_at=f"2024-01-{i + 1:02d}T00:00:00+00:00",
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# acceptance scenarios
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="memory", scenario="the composed context stays within its token budget"
)
async def test_composed_context_stays_within_its_token_budget() -> None:
    facts = _many_project_facts(80)
    memory = FakeMemory(
        visible=[GLOBAL_PARTITION, "myproj"],
        facts={"myproj": facts},
        partitions=[PartitionSummary(name="myproj", project_root="/repo/myproj", fact_count=80)],
    )
    budget = 200
    ctx = await compose_context(memory, agent=None, cwd="/repo/myproj", budget_tokens=budget)
    assert estimate_tokens(ctx.text) <= budget
    assert ctx.facts_included < len(facts)


@pytest.mark.acceptance(
    spec="memory", scenario="the composed context says how many facts it left out"
)
async def test_composed_context_says_how_many_facts_it_left_out() -> None:
    facts = _many_project_facts(50)
    memory = FakeMemory(
        visible=[GLOBAL_PARTITION, "myproj"],
        facts={"myproj": facts},
        partitions=[PartitionSummary(name="myproj", project_root="/repo/myproj", fact_count=50)],
    )
    ctx = await compose_context(memory, agent=None, cwd="/repo/myproj", budget_tokens=150)
    assert ctx.facts_omitted > 0
    assert str(ctx.facts_omitted) in ctx.text
    assert "coffer__recall" in ctx.text


async def test_the_pointer_asks_for_the_kind_of_query_recall_can_actually_answer() -> None:
    """FR-060: recall matches LITERALLY, and its own tool description says so.

    The pointer is the first thing an agent reads every session, and it used to
    ask for "a natural-language query" — the one shape a case-insensitive
    substring scan cannot answer. An agent that followed it sent a whole
    question and got nothing back, which reads as an empty memory rather than a
    misused tool. Asserted in both directions: the wording that misleads must be
    gone, and the wording that guides must be there.
    """
    memory = FakeMemory(
        visible=[GLOBAL_PARTITION, "myproj"],
        facts={"myproj": _many_project_facts(50)},
        partitions=[PartitionSummary(name="myproj", project_root="/repo/myproj", fact_count=50)],
    )

    trimmed = await compose_context(memory, agent=None, cwd="/repo/myproj", budget_tokens=150)
    whole = await compose_context(memory, agent=None, cwd="/repo/myproj", budget_tokens=100_000)
    assert trimmed.facts_omitted > 0 and whole.facts_omitted == 0

    for ctx in (trimmed, whole):
        assert "natural-language" not in ctx.text, ctx.text
        assert "natural language" not in ctx.text, ctx.text
        # The word the tool's own description uses, so the two agree.
        assert "literal" in ctx.text.lower(), ctx.text


# ---------------------------------------------------------------------------
# preference order
# ---------------------------------------------------------------------------


async def test_the_budget_is_spent_on_the_most_recent_facts_first() -> None:
    """FR-051's whole within-partition order, now that pinning is gone.

    Pinning used to sit in front of recency; the developer's overrides were
    deleted with the per-fact surface, so recency is the only preference left
    and a trim must take the oldest facts rather than an arbitrary set.
    """
    facts = _many_project_facts(30)
    newest = facts[-1]  # captured_at "2024-01-30" — first in recency order
    oldest = facts[0]
    memory = FakeMemory(
        visible=[GLOBAL_PARTITION, "myproj"],
        facts={"myproj": facts},
        partitions=[PartitionSummary(name="myproj", project_root="/repo/myproj", fact_count=30)],
    )

    ctx = await compose_context(memory, agent=None, cwd="/repo/myproj", budget_tokens=140)

    assert newest.title in ctx.text
    assert oldest.title not in ctx.text


# ---------------------------------------------------------------------------
# cwd resolution
# ---------------------------------------------------------------------------


async def test_an_unknown_cwd_yields_global_only() -> None:
    global_fact = _fact(
        slug="pref", partition=GLOBAL_PARTITION, title="Prefers Chinese replies", type_=TYPE_USER
    )
    project_facts = _many_project_facts(5)
    memory = FakeMemory(
        visible=[GLOBAL_PARTITION, "myproj"],
        facts={GLOBAL_PARTITION: [global_fact], "myproj": project_facts},
        partitions=[PartitionSummary(name="myproj", project_root="/repo/myproj", fact_count=5)],
    )

    ctx = await compose_context(memory, agent=None, cwd="/somewhere/totally/unrelated")

    assert ctx.partition == GLOBAL_PARTITION
    assert ctx.layers == (LAYER_L0,)
    assert "Prefers Chinese replies" in ctx.text
    assert project_facts[0].title not in ctx.text


async def test_cwd_under_a_registered_project_root_resolves_to_it() -> None:
    facts = _many_project_facts(2)
    memory = FakeMemory(
        visible=[GLOBAL_PARTITION, "myproj"],
        facts={"myproj": facts},
        partitions=[PartitionSummary(name="myproj", project_root="/repo/myproj", fact_count=2)],
    )

    ctx = await compose_context(memory, agent=None, cwd="/repo/myproj/backend/coffer")

    assert ctx.partition == "myproj"


# ---------------------------------------------------------------------------
# layering
# ---------------------------------------------------------------------------


async def test_l1_is_dropped_when_it_does_not_fit_and_l0_still_ships() -> None:
    facts = _many_project_facts(20)
    memory = FakeMemory(
        visible=[GLOBAL_PARTITION, "myproj"],
        facts={"myproj": facts},
        partitions=[PartitionSummary(name="myproj", project_root="/repo/myproj", fact_count=20)],
    )

    ctx = await compose_context(memory, agent=None, cwd="/repo/myproj", budget_tokens=55)

    assert ctx.layers == (LAYER_L0,)
    assert ctx.facts_included == 0
    assert ctx.facts_omitted == len(facts)
    assert "## Coffer memory" in ctx.text
    assert "coffer__recall" in ctx.text
    for fact in facts:
        assert fact.title not in ctx.text


async def test_l1_appears_when_the_budget_allows_it() -> None:
    facts = _many_project_facts(3)
    memory = FakeMemory(
        visible=[GLOBAL_PARTITION, "myproj"],
        facts={"myproj": facts},
        partitions=[PartitionSummary(name="myproj", project_root="/repo/myproj", fact_count=3)],
    )

    ctx = await compose_context(memory, agent=None, cwd="/repo/myproj")

    assert LAYER_L1 in ctx.layers
    assert ctx.facts_omitted == 0
    for fact in facts:
        assert fact.title in ctx.text


def test_composed_context_is_a_frozen_dataclass() -> None:
    ctx = ComposedContext(
        text="x", partition="global", facts_included=0, facts_omitted=0, layers=()
    )
    with pytest.raises(Exception):  # noqa: B017 - frozen dataclass raises FrozenInstanceError
        ctx.text = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# one renderer, two outputs
# ---------------------------------------------------------------------------
#
# FR-050 calls L1 "the partition's digest, one line per fact" — the same
# concept `summary.md` is made of. These two tests are the guard against the
# two ever drifting apart again: they render the same facts through
# `render_digest` and through `compose_context` and demand the fact lines come
# out character-for-character identical, so a change to one renderer that is
# not a change to the other fails here rather than in a person's session.


def _digest_fact_lines(facts: Sequence[Fact], *, partition: str) -> list[str]:
    lines = [
        line
        for line in render_digest(facts, partition=partition).splitlines()
        if line.startswith("- ")
    ]
    assert lines, "render_digest produced no fact lines to compare against"
    return lines


async def test_a_fact_timestamped_only_by_its_source_still_sorts_by_that() -> None:
    """The two modules agreed on the LINE and still disagreed on the ORDER.

    `digest._recency` falls back to `source_written_at` when `captured_at` is
    absent; this module's did not, so such a fact scored `""` and sorted last
    here while sorting correctly in `summary.md` — the same drift as the line
    shape, one layer down. Nothing in FR-032 or FR-051 distinguishes the two
    timestamps, so neither should the code.
    """
    newest_by_source = Fact(
        slug="from-source",
        title="Timestamped by its source only",
        description="No captured_at on this origin.",
        type=TYPE_PROJECT,
        body="body",
        partition="myproj",
        origins=(
            Origin(
                agent="codex",
                native_path="/native/from-source.md",
                captured_at="",
                source_written_at="2030-01-01T00:00:00+00:00",
            ),
        ),
    )
    older = _fact(slug="older", partition="myproj", captured_at="2020-01-01T00:00:00+00:00")
    memory = FakeMemory(
        visible=[GLOBAL_PARTITION, "myproj"],
        facts={"myproj": [older, newest_by_source]},
        partitions=[PartitionSummary(name="myproj", project_root="/repo/myproj", fact_count=2)],
    )

    ctx = await compose_context(memory, agent=None, cwd="/repo/myproj", budget_tokens=100_000)

    lines = [line for line in ctx.text.splitlines() if line.startswith("- ")]
    assert lines.index("- **Timestamped by its source only** — No captured_at on this origin.") < (
        lines.index("- **older** — A fact worth knowing.")
    ), ctx.text


@pytest.mark.parametrize("description", ["A fact worth knowing.", ""])
async def test_l1_fact_lines_are_the_digest_renderer_s_own_lines(description: str) -> None:
    facts = [
        _fact(
            slug="worktrees",
            partition="myproj",
            title="Develops in a worktree",
            description=description,
        ),
        _fact(
            slug="chinese",
            partition="myproj",
            title="Prefers Chinese replies",
            description=description,
        ),
    ]
    memory = FakeMemory(
        visible=[GLOBAL_PARTITION, "myproj"],
        facts={"myproj": facts},
        partitions=[PartitionSummary(name="myproj", project_root="/repo/myproj", fact_count=2)],
    )

    ctx = await compose_context(memory, agent=None, cwd="/repo/myproj")

    assert LAYER_L1 in ctx.layers
    for line in _digest_fact_lines(facts, partition="myproj"):
        assert line in ctx.text, f"{line!r} not in:\n{ctx.text}"


async def test_global_fact_lines_are_the_digest_renderer_s_own_lines() -> None:
    facts = [
        _fact(
            slug="chinese",
            partition=GLOBAL_PARTITION,
            title="Prefers Chinese replies",
            type_=TYPE_USER,
        )
    ]
    memory = FakeMemory(visible=[GLOBAL_PARTITION], facts={GLOBAL_PARTITION: facts})

    ctx = await compose_context(memory, agent=None, cwd="/somewhere/unregistered")

    assert ctx.facts_included == 1
    for line in _digest_fact_lines(facts, partition=GLOBAL_PARTITION):
        assert line in ctx.text, f"{line!r} not in:\n{ctx.text}"
