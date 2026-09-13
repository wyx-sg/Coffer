"""Unit tests for composing the session-start context (application/memory/context.py).

Every ``MemoryPort``/``OverridesPort`` here is a plain in-memory fake — no
database, no filesystem — which is exactly what the two narrow Protocols in
``context.py`` are for. No env pinning is needed either: this module never
touches ``$COFFER_MEMORY_ROOT`` at all.
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
from coffer.application.memory.overrides import Override
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


class FakeOverrides:
    def __init__(self, overrides: Mapping[str, Override] | None = None) -> None:
        self._overrides = dict(overrides or {})

    async def all(self) -> Mapping[str, Override]:
        return self._overrides


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
    ctx = await compose_context(
        memory, FakeOverrides(), agent=None, cwd="/repo/myproj", budget_tokens=budget
    )
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
    ctx = await compose_context(
        memory, FakeOverrides(), agent=None, cwd="/repo/myproj", budget_tokens=150
    )
    assert ctx.facts_omitted > 0
    assert str(ctx.facts_omitted) in ctx.text
    assert "coffer__recall" in ctx.text


# ---------------------------------------------------------------------------
# overrides
# ---------------------------------------------------------------------------


async def test_a_hidden_fact_never_appears() -> None:
    visible_fact = _fact(slug="keep", partition=GLOBAL_PARTITION, title="Keep This")
    hidden_fact = _fact(slug="hide", partition=GLOBAL_PARTITION, title="Hide This Secret")
    memory = FakeMemory(
        visible=[GLOBAL_PARTITION], facts={GLOBAL_PARTITION: [visible_fact, hidden_fact]}
    )
    overrides = FakeOverrides({hidden_fact.key: Override(fact_key=hidden_fact.key, hidden=True)})

    ctx = await compose_context(memory, overrides, agent=None, cwd="")

    assert "Keep This" in ctx.text
    assert "Hide This Secret" not in ctx.text


async def test_a_pinned_fact_survives_trimming_that_drops_others() -> None:
    facts = _many_project_facts(30)
    oldest = facts[0]  # captured_at "2024-01-01" — last in recency order
    second_oldest = facts[1]
    memory = FakeMemory(
        visible=[GLOBAL_PARTITION, "myproj"],
        facts={"myproj": facts},
        partitions=[PartitionSummary(name="myproj", project_root="/repo/myproj", fact_count=30)],
    )
    overrides = FakeOverrides({oldest.key: Override(fact_key=oldest.key, pinned=True)})

    ctx = await compose_context(
        memory, overrides, agent=None, cwd="/repo/myproj", budget_tokens=140
    )

    assert oldest.title in ctx.text
    assert second_oldest.title not in ctx.text


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

    ctx = await compose_context(
        memory, FakeOverrides(), agent=None, cwd="/somewhere/totally/unrelated"
    )

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

    ctx = await compose_context(
        memory, FakeOverrides(), agent=None, cwd="/repo/myproj/backend/coffer"
    )

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

    ctx = await compose_context(
        memory, FakeOverrides(), agent=None, cwd="/repo/myproj", budget_tokens=55
    )

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

    ctx = await compose_context(memory, FakeOverrides(), agent=None, cwd="/repo/myproj")

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
