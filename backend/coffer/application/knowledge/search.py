"""Ranked retrieval over the knowledge files — and the literal search it falls
back to.

The mechanics — keep a disposable sidecar fresh, embed a query, rank, degrade
to literal on any failure — moved to ``coffer.application.ranked_retrieval``
once memory's ``coffer__recall`` needed the identical loop over a different
corpus (spec memory FR-052). This module now does exactly what is left that
*is* knowledge-specific: resolve which collections one caller may see
(``_scope``), list the files under them, and answer the FR-027 fallback with
knowledge's own ripgrep. Its public API and behaviour are unchanged by that
move — every existing test here and in the integration suite passes without
modification, which is how the extraction is proven behaviour-preserving.

Two consequences worth restating, because they are what keep the deleted
index stack from coming back in disguise:

* **Freshness is decided from the file, never from a record of an edit.**
  There is no reindex step to forget and no write path to hook, so a file the
  human changed in their editor, an agent wrote, or `git` pulled all look the
  same to this module (FR-028).
* **The sidecar is never authoritative.** It is consulted for ordering and
  nothing else; titles, descriptions and content always come off disk.
"""

from __future__ import annotations

from collections.abc import Sequence

from coffer.application.knowledge.service import KnowledgeService
from coffer.application.ranked_retrieval import (
    DEFAULT_TOP_K,
    EmbedderFactory,
    Hit,
    Outcome,
    RankedRetrieval,
    RetrievalMode,
    RetrievedFile,
    Scope,
    Status,
)
from coffer.domain.knowledge.errors import CollectionNotFound
from coffer.infrastructure.knowledge import fs, paths

#: Re-exported under their historical names: everything outside this module
#: (``knowledge_wiring``, ``builtin_search_tool``, the REST routes, both
#: search test suites) imports these from here, and the extraction changes
#: nothing about their shape.
SearchHit = Hit
SearchOutcome = Outcome
SearchMode = RetrievalMode
IndexStatus = Status

#: Lines of a matched line quoted back per literal hit — mirrors
#: ``ranked_retrieval``'s own excerpt size for the ranked path.
_EXCERPT_LINES = 4

__all__ = [
    "EmbedderFactory",
    "IndexStatus",
    "SearchHit",
    "SearchMode",
    "SearchOutcome",
    "SearchService",
]


def _read_file(relpath: str) -> RetrievedFile:
    entry = fs.read_file(relpath)
    return RetrievedFile(
        path=entry.path, title=entry.title, description=entry.description, body=entry.body
    )


def _paths_under(collections: Sequence[str]) -> set[str]:
    """Every content file in ``collections``, as knowledge-root-relative paths."""
    found: set[str] = set()
    for name in collections:
        found.update(fs.iter_files(name))
    return found


class SearchService:
    """Answers a natural-language query over the collections a caller may see."""

    def __init__(
        self,
        *,
        knowledge: KnowledgeService,
        embedder_factory: EmbedderFactory,
    ) -> None:
        self._knowledge = knowledge
        self._engine = RankedRetrieval(
            namespace="knowledge",
            resolve=paths.resolve,
            read_file=_read_file,
            embedder_factory=embedder_factory,
        )

    # ----- the one public operation --------------------------------------

    async def search(
        self,
        query: str,
        *,
        agent: str | None = None,
        collection: str | None = None,
        top_k: int = DEFAULT_TOP_K,
    ) -> SearchOutcome:
        collections = await self._scope(agent, collection)
        return await self._engine.search(query, self._scope_of(collections, agent), top_k=top_k)

    # ----- index maintenance ---------------------------------------------

    async def rebuild(self, *, agent: str | None = None) -> IndexStatus:
        """Re-embed every visible file from scratch, discarding what is there."""
        collections = await self._scope(agent, None)
        return await self._engine.rebuild(self._scope_of(collections, agent))

    async def status(self, *, agent: str | None = None) -> IndexStatus:
        collections = await self._scope(agent, None)
        return await self._engine.status(self._scope_of(collections, agent))

    # ----- internals -------------------------------------------------------

    async def _scope(self, agent: str | None, collection: str | None) -> list[str]:
        visible = await self._knowledge.visible_collections(agent)
        if collection is None:
            return visible
        if collection not in visible:
            raise CollectionNotFound(collection)
        return [collection]

    def _scope_of(self, collections: Sequence[str], agent: str | None) -> Scope:
        """Build one call's :class:`Scope` — the files under ``collections``,
        which of them this call may prune, and how to answer literally
        within exactly this boundary.
        """
        present = frozenset(_paths_under(collections))
        walked = set(collections)

        async def list_present() -> frozenset[str]:
            return present

        def owns(path: str) -> bool:
            return paths.collection_of(path) in walked

        async def literal_fallback(query: str, top_k: int, reason: str) -> SearchOutcome:
            return await self._literal(query, agent, collections, top_k, reason)

        return Scope(list_present=list_present, owns=owns, literal_fallback=literal_fallback)

    async def _literal(
        self,
        query: str,
        agent: str | None,
        collections: Sequence[str],
        top_k: int,
        reason: str,
    ) -> SearchOutcome:
        """The FR-027 fallback: ripgrep, reported as what it is.

        The agent is passed through rather than dropped, so the fallback reads
        exactly the collections the ranked path would have — a degraded answer
        must not be a wider one.
        """
        outcome = await self._knowledge.grep(query, agent=agent)
        wanted = set(collections)
        by_path: dict[str, list[tuple[int, str]]] = {}
        for match in outcome.matches:
            if paths.collection_of(match.path) not in wanted:
                continue
            by_path.setdefault(match.path, []).append((match.line_number, match.line))
        hits: list[SearchHit] = []
        for path, matched in list(by_path.items())[:top_k]:
            entry = fs.read_file(path)
            hits.append(
                SearchHit(
                    path=path,
                    title=entry.title,
                    description=entry.description,
                    score=None,
                    heading="",
                    excerpt=tuple(matched[:_EXCERPT_LINES]),
                )
            )
        return SearchOutcome(hits=tuple(hits), mode="literal", reason=reason)
