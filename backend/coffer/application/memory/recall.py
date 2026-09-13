"""``coffer__recall`` — memory's L2 layer (spec memory FR-052, FR-060).

L0/L1 (``context.py``) are a small, budgeted push; this is the pull that
answers whatever they left out. It reuses knowledge's ranked-retrieval loop
wholesale (``coffer.application.ranked_retrieval``) rather than
reimplementing "embed, rank, degrade to literal with no connection" a second
time — the very reuse FR-052 names by spec section (knowledge FR-025..029).

The literal fallback here is **not** knowledge's ripgrep-over-files: the
memory kind has no standing import of the knowledge kind's ripgrep wrapper
(only the disposable-sidecar substrate is shared, via ``ranked_retrieval``),
and at the corpus size spec memory itself assumes — "hundreds of facts per
partition" — a plain case-insensitive substring scan over facts already
loaded in memory is simpler than shelling out, and just as correct. It never
raises and never returns empty for want of a connection (FR-052).
"""

from __future__ import annotations

import pathlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from coffer.application.memory.overrides import Override, apply
from coffer.application.ranked_retrieval import (
    DEFAULT_TOP_K,
    EmbedderFactory,
    Hit,
    Outcome,
    RankedRetrieval,
    RetrievedFile,
    Scope,
)
from coffer.domain.memory.fact import Fact
from coffer.infrastructure.memory import paths as memory_paths
from coffer.infrastructure.memory import store as memory_store

#: Lines of a fact's body quoted back per literal hit — mirrors
#: ``ranked_retrieval``'s own excerpt size for the ranked path.
_EXCERPT_LINES = 4


class MemoryPort(Protocol):
    """The slice of ``MemoryService`` recall needs: scope and reads, never
    aggregation. Matches ``MemoryService``'s real signatures structurally,
    so a unit test can fake it with no database at all."""

    async def visible_partitions(self, agent: str | None) -> Sequence[str]: ...

    async def list_facts(self, partition: str, *, agent: str | None = None) -> Sequence[Fact]: ...


class OverridesPort(Protocol):
    """Every developer decision at once — the shape ``overrides.apply``
    wants, and the only one recall needs (never a single lookup or a write)."""

    async def all(self) -> Mapping[str, Override]: ...


@dataclass(frozen=True)
class RecalledFact:
    """One fact ``recall`` answers with — its origins intact (FR-052)."""

    path: str
    title: str
    description: str
    body: str
    type: str
    partition: str
    #: ``(agent, native_path)`` per place this fact was seen.
    origins: tuple[tuple[str, str], ...]
    #: Cosine score in ranked mode; ``None`` when the answer is literal.
    score: float | None


@dataclass(frozen=True)
class RecallOutcome:
    facts: tuple[RecalledFact, ...]
    mode: str  # "ranked" | "literal"
    reason: str = ""


def _relpath(fact: Fact) -> str:
    """The fact file's memory-root-relative path — recall's identity for the
    ranked-retrieval sidecar, the same role a knowledge file's own path
    plays there."""
    return memory_paths.relative_of(memory_paths.fact_path(fact.partition, fact.slug))


def _parse_relpath(relpath: str) -> tuple[str, str]:
    """Inverse of :func:`_relpath`: ``<partition>/facts/<slug>.md`` ->
    ``(partition, slug)``."""
    segments = relpath.split("/")
    return segments[0], pathlib.Path(segments[-1]).stem


class RecallService:
    def __init__(
        self,
        *,
        memory: MemoryPort,
        overrides: OverridesPort,
        embedder_factory: EmbedderFactory,
    ) -> None:
        self._memory = memory
        self._overrides = overrides
        self._engine = RankedRetrieval(
            namespace="memory",
            resolve=lambda relpath: memory_paths.fact_path(*_parse_relpath(relpath)),
            read_file=self._read_file,
            embedder_factory=embedder_factory,
        )

    def _read_file(self, relpath: str) -> RetrievedFile:
        partition, slug = _parse_relpath(relpath)
        fact = memory_store.read_fact(partition, slug)
        return RetrievedFile(
            path=relpath, title=fact.title, description=fact.description, body=fact.body
        )

    async def recall(
        self, query: str, *, agent: str | None = None, top_k: int = DEFAULT_TOP_K
    ) -> RecallOutcome:
        visible = await self._memory.visible_partitions(agent)
        raw: dict[str, Fact] = {}
        for partition in visible:
            for fact in await self._memory.list_facts(partition, agent=agent):
                raw[_relpath(fact)] = fact

        applied = apply(list(raw.values()), await self._overrides.all())
        shown_keys = {f.key for f in applied.visible()}
        by_path = {path: fact for path, fact in raw.items() if fact.key in shown_keys}
        present = frozenset(by_path)
        walked = frozenset(visible)

        async def list_present() -> frozenset[str]:
            return present

        def owns(path: str) -> bool:
            partition, _ = _parse_relpath(path)
            return partition in walked

        async def literal_fallback(q: str, k: int, reason: str) -> Outcome:
            return self._literal(q, by_path, k, reason)

        outcome = await self._engine.search(
            query,
            Scope(list_present=list_present, owns=owns, literal_fallback=literal_fallback),
            top_k=top_k,
        )
        return self._to_recall_outcome(outcome, by_path)

    def _literal(self, query: str, by_path: Mapping[str, Fact], top_k: int, reason: str) -> Outcome:
        """The FR-052 fallback: a substring scan over facts already in hand."""
        needle = query.strip().lower()
        matches: list[tuple[str, tuple[tuple[int, str], ...]]] = []
        for path, fact in by_path.items():
            lines = fact.body.splitlines()
            found = [(i + 1, line) for i, line in enumerate(lines) if needle in line.lower()]
            if not found and needle in f"{fact.title} {fact.description}".lower():
                found = [(0, fact.description or fact.title)]
            if found:
                matches.append((path, tuple(found[:_EXCERPT_LINES])))
        matches.sort(key=lambda m: m[0])
        hits = tuple(
            Hit(
                path=path,
                title=by_path[path].title,
                description=by_path[path].description,
                score=None,
                heading="",
                excerpt=excerpt,
            )
            for path, excerpt in matches[:top_k]
        )
        return Outcome(hits=hits, mode="literal", reason=reason)

    def _to_recall_outcome(self, outcome: Outcome, by_path: Mapping[str, Fact]) -> RecallOutcome:
        facts = tuple(
            RecalledFact(
                path=hit.path,
                title=hit.title,
                description=hit.description,
                body=by_path[hit.path].body,
                type=by_path[hit.path].type,
                partition=by_path[hit.path].partition,
                origins=tuple((o.agent, o.native_path) for o in by_path[hit.path].origins),
                score=hit.score,
            )
            for hit in outcome.hits
            if hit.path in by_path
        )
        return RecallOutcome(facts=facts, mode=outcome.mode, reason=outcome.reason)


__all__ = ["MemoryPort", "OverridesPort", "RecallOutcome", "RecallService", "RecalledFact"]
