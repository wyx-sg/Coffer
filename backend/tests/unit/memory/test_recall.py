"""Unit tests for ``coffer__recall`` (application/memory/recall.py).

``COFFER_MEMORY_ROOT`` is pinned to ``tmp_path`` by the suite-wide
``_isolated_memory_root`` fixture (``backend/tests/conftest.py``);
``COFFER_INDEX_ROOT`` — the disposable sidecar recall shares with knowledge
(spec memory FR-052) — is pinned locally below, since only knowledge's own
suite pins it globally. Facts are written for real with
``infrastructure.memory.store.write_fact`` so ``RecallService`` reads back
real files, exactly as it does in production; only the ``MemoryPort``
(scope) and the embedder are faked.
"""

from __future__ import annotations

import pathlib
from collections.abc import Sequence

import pytest

from coffer.application.memory.overrides import Override
from coffer.application.memory.recall import RecallService
from coffer.domain.memory.fact import TYPE_PROJECT, Fact, Origin
from coffer.infrastructure.memory import store


@pytest.fixture(autouse=True)
def _pin_index_root(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COFFER_INDEX_ROOT", str(tmp_path / "index-root"))


def _fact(*, slug: str, partition: str, title: str, description: str, body: str) -> Fact:
    return Fact(
        slug=slug,
        title=title,
        description=description,
        type=TYPE_PROJECT,
        body=body,
        partition=partition,
        origins=(
            Origin(
                agent="claude_code",
                native_path=f"/native/{partition}/{slug}.md",
                captured_at="2024-01-01T00:00:00+00:00",
            ),
        ),
    )


def _persist(fact: Fact) -> Fact:
    """Write a fact for real and read it back, so it carries whatever the
    round trip normalises (mirrors ``test_store.py``'s own pattern)."""
    store.write_fact(fact)
    return store.read_fact(fact.partition, fact.slug)


class FakeMemory:
    """A ``MemoryPort`` whose scope is keyed by agent identity."""

    def __init__(self, *, visible_by_agent: dict[str | None, Sequence[str]]) -> None:
        self._visible_by_agent = visible_by_agent

    async def visible_partitions(self, agent: str | None) -> Sequence[str]:
        return self._visible_by_agent.get(agent, ())

    async def list_facts(self, partition: str, *, agent: str | None = None) -> Sequence[Fact]:
        return store.list_facts(partition)


class FakeOverrides:
    def __init__(self, overrides: dict[str, Override] | None = None) -> None:
        self._overrides = dict(overrides or {})

    async def all(self) -> dict[str, Override]:
        return self._overrides


async def _no_embedder():
    return None


def _service(memory: FakeMemory, overrides: FakeOverrides | None = None) -> RecallService:
    return RecallService(
        memory=memory, overrides=overrides or FakeOverrides(), embedder_factory=_no_embedder
    )


# ---------------------------------------------------------------------------
# acceptance scenarios
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="memory", scenario="recall falls back to literal matching with no internal connection"
)
async def test_recall_falls_back_to_literal_matching_with_no_internal_connection() -> None:
    _persist(
        _fact(
            slug="pip-mirror",
            partition="coffer",
            title="Local pip mirror is unreachable",
            description="Use public PyPI instead",
            body="This machine's pip points at an unreachable internal mirror.",
        )
    )
    service = _service(FakeMemory(visible_by_agent={None: ["coffer"]}))

    outcome = await service.recall("unreachable internal mirror")

    assert outcome.mode == "literal"
    assert outcome.reason
    assert any(f.title == "Local pip mirror is unreachable" for f in outcome.facts)


@pytest.mark.acceptance(
    spec="memory", scenario="recall spans only the partitions the calling agent may see"
)
async def test_recall_spans_only_the_partitions_the_calling_agent_may_see() -> None:
    _persist(
        _fact(
            slug="alpha-secret",
            partition="alpha",
            title="Alpha internal detail",
            description="d",
            body="This entry carries the codeword scopemarker for alpha only.",
        )
    )
    _persist(
        _fact(
            slug="beta-note",
            partition="beta",
            title="Beta internal detail",
            description="d",
            body="This entry carries the codeword scopemarker for beta only.",
        )
    )
    service = _service(FakeMemory(visible_by_agent={"agent-a": ["alpha"], "agent-b": ["beta"]}))

    outcome = await service.recall("scopemarker", agent="agent-a")

    titles = {f.title for f in outcome.facts}
    assert "Alpha internal detail" in titles
    assert "Beta internal detail" not in titles


@pytest.mark.acceptance(spec="memory", scenario="recall returns facts the digest omitted")
async def test_recall_returns_facts_the_digest_omitted() -> None:
    from coffer.application.memory.context import compose_context
    from coffer.application.memory.service import PartitionSummary
    from coffer.domain.memory.partition import GLOBAL_PARTITION

    for i in range(40):
        _persist(
            _fact(
                slug=f"fact-{i}",
                partition="myproj",
                title=f"Fact number {i}",
                description="A long description padded so the digest fills up fast.",
                body=(
                    "Ordinary content."
                    if i != 0
                    else "This one carries the codeword needleinahaystack for lookup."
                ),
            )
        )

    class _ContextMemory:
        async def visible_partitions(self, agent: str | None) -> Sequence[str]:
            return [GLOBAL_PARTITION, "myproj"]

        async def list_facts(self, partition: str, *, agent: str | None = None) -> Sequence[Fact]:
            return store.list_facts(partition) if partition == "myproj" else ()

        async def list_partitions(self) -> Sequence[PartitionSummary]:
            return [PartitionSummary(name="myproj", project_root="/repo/myproj", fact_count=40)]

    ctx = await compose_context(
        _ContextMemory(), FakeOverrides(), agent=None, cwd="/repo/myproj", budget_tokens=150
    )
    # The digest is small; confirm the specific fact we will recall is not in it.
    assert "needleinahaystack" not in ctx.text
    assert ctx.facts_omitted > 0

    service = _service(FakeMemory(visible_by_agent={None: ["myproj"]}))
    outcome = await service.recall("needleinahaystack")

    assert any("needleinahaystack" in f.body for f in outcome.facts)


# ---------------------------------------------------------------------------
# other coverage
# ---------------------------------------------------------------------------


async def test_recall_excludes_a_hidden_fact() -> None:
    fact = _persist(
        _fact(
            slug="hidden-one",
            partition="coffer",
            title="Should stay hidden",
            description="d",
            body="This entry carries the codeword hiddenmarker.",
        )
    )
    overrides = FakeOverrides({fact.key: Override(fact_key=fact.key, hidden=True)})
    service = _service(FakeMemory(visible_by_agent={None: ["coffer"]}), overrides)

    outcome = await service.recall("hiddenmarker")

    assert outcome.facts == ()


async def test_recall_reports_origins_on_returned_facts() -> None:
    _persist(
        _fact(
            slug="with-origin",
            partition="coffer",
            title="Traceable fact",
            description="d",
            body="This entry carries the codeword traceorigin.",
        )
    )
    service = _service(FakeMemory(visible_by_agent={None: ["coffer"]}))

    outcome = await service.recall("traceorigin")

    assert outcome.facts
    fact = outcome.facts[0]
    assert fact.origins == (("claude_code", "/native/coffer/with-origin.md"),)


async def test_recall_returns_no_facts_for_an_empty_corpus() -> None:
    service = _service(FakeMemory(visible_by_agent={None: []}))
    outcome = await service.recall("anything")
    assert outcome.facts == ()
