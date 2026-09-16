"""``coffer__recall`` — memory's L2 layer (spec memory FR-023, FR-027).

L0/L1 (``context.py``) are a small, budgeted push; this is the pull that
answers whatever they left out. It used to reuse knowledge's ranked-retrieval
loop — embed the query, rank facts by cosine, degrade to literal matching when
no embedder was available. That loop is **gone**, deliberately removed along
with every other use of embeddings in Coffer. What is left is the tier that was
previously the fallback, promoted to being the whole answer: a plain
case-insensitive substring scan over the facts this caller may see, already
loaded in memory.

That scan stays memory's own rather than borrowing knowledge's ripgrep: at the
corpus size spec memory assumes — "hundreds of facts per partition" — the facts
are in hand already and shelling out buys nothing, and the memory kind has no
standing import of the knowledge kind's search substrate regardless. It never
raises and never returns empty for want of a connection, because there is no
connection left for it to want (FR-023).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from coffer.domain.memory.fact import Fact
from coffer.infrastructure.memory import paths as memory_paths

#: Facts returned per call — the same ceiling knowledge's ``search`` uses, kept
#: as its own constant rather than imported so the two kinds' pull tools do not
#: import each other over one integer.
DEFAULT_TOP_K = 8


class MemoryPort(Protocol):
    """The slice of ``MemoryService`` recall needs: scope and reads, never
    aggregation. Matches ``MemoryService``'s real signatures structurally,
    so a unit test can fake it with no database at all."""

    async def visible_partitions(self, agent: str | None) -> Sequence[str]: ...

    async def list_facts(self, partition: str, *, agent: str | None = None) -> Sequence[Fact]: ...


@dataclass(frozen=True)
class RecalledFact:
    """One fact ``recall`` answers with — its origins intact (FR-023)."""

    path: str
    title: str
    description: str
    body: str
    type: str
    partition: str
    #: ``(agent, native_path)`` per place this fact was seen.
    origins: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class RecallOutcome:
    facts: tuple[RecalledFact, ...]


def _relpath(fact: Fact) -> str:
    """The fact file's memory-root-relative path — recall's identity for a
    fact, the same role a knowledge file's own path plays in ``search``."""
    return memory_paths.relative_of(memory_paths.fact_path(fact.partition, fact.slug))


class RecallService:
    def __init__(self, *, memory: MemoryPort) -> None:
        self._memory = memory

    async def recall(
        self, query: str, *, agent: str | None = None, top_k: int = DEFAULT_TOP_K
    ) -> RecallOutcome:
        visible = await self._memory.visible_partitions(agent)
        by_path: dict[str, Fact] = {}
        for partition in visible:
            for fact in await self._memory.list_facts(partition, agent=agent):
                by_path[_relpath(fact)] = fact

        if not by_path or not query.strip():
            return RecallOutcome(facts=())
        return self._literal(query.strip(), by_path, top_k)

    def _literal(self, query: str, by_path: Mapping[str, Fact], top_k: int) -> RecallOutcome:
        """A substring scan over the facts already in hand (FR-023).

        A fact matches on its body first; failing that, on its title or
        description, so a fact whose one-line summary is the only place the
        words appear is still recallable.
        """
        needle = query.lower()
        matched: list[str] = []
        for path, fact in by_path.items():
            lines = fact.body.splitlines()
            found = any(needle in line.lower() for line in lines)
            if found or needle in f"{fact.title} {fact.description}".lower():
                matched.append(path)
        matched.sort()
        return RecallOutcome(
            facts=tuple(self._recalled(by_path[path], path) for path in matched[:top_k])
        )

    @staticmethod
    def _recalled(fact: Fact, path: str) -> RecalledFact:
        return RecalledFact(
            path=path,
            title=fact.title,
            description=fact.description,
            body=fact.body,
            type=fact.type,
            partition=fact.partition,
            origins=tuple((o.agent, o.native_path) for o in fact.origins),
        )


__all__ = [
    "DEFAULT_TOP_K",
    "MemoryPort",
    "RecallOutcome",
    "RecallService",
    "RecalledFact",
]
