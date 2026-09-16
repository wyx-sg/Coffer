"""``coffer__search`` — literal search over the knowledge files.

Ripgrep over exactly the collections the caller may see, reported as file-level
hits with the lines that matched. Two properties follow from having no index at
all, and they are why there is nothing here to keep level with the disk:

* **Freshness is decided from the file, never from a record of an edit.** A
  file the human changed in their editor, an agent wrote, or `git` pulled is
  searchable the instant it lands (FR-028).
* **Nothing derived is authoritative.** Titles, descriptions and content always
  come off disk, because there is nowhere else they could come from.

What is knowledge-specific, and therefore still lives here: resolving which
collections one caller may see (:meth:`SearchService._scope`) and shaping
``KnowledgeService.grep``'s line matches into per-file hits.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.knowledge.errors import CollectionNotFound
from coffer.infrastructure.knowledge import fs, paths

#: Files returned per call. The catalogue already answers "what exists" a level
#: at a time (FR-021); this is ``search``'s analogue — enough results to scan on
#: one screen without turning a query into a second full-corpus dump. A caller
#: that wants fewer passes a smaller ``top_k``.
DEFAULT_TOP_K = 8

#: Matched lines quoted back per hit — enough to see why the file matched, not
#: enough to be a substitute for reading it.
_EXCERPT_LINES = 4

__all__ = [
    "DEFAULT_TOP_K",
    "SearchHit",
    "SearchOutcome",
    "SearchService",
]


@dataclass(frozen=True)
class SearchHit:
    """One file a search answered with, and the lines that matched in it."""

    path: str
    title: str
    description: str
    #: The matching lines worth showing, each ``(line_number, text)``.
    excerpt: tuple[tuple[int, str], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SearchOutcome:
    """What a search answered."""

    hits: tuple[SearchHit, ...]


class SearchService:
    """Answers a text query over the collections a caller may see."""

    def __init__(self, *, knowledge: KnowledgeService) -> None:
        self._knowledge = knowledge

    async def search(
        self,
        query: str,
        *,
        agent: str | None = None,
        collection: str | None = None,
        top_k: int = DEFAULT_TOP_K,
    ) -> SearchOutcome:
        collections = await self._scope(agent, collection)
        if not collections or not query.strip():
            return SearchOutcome(hits=())
        return await self._literal(query.strip(), agent, collections, top_k)

    # ----- internals -------------------------------------------------------

    async def _scope(self, agent: str | None, collection: str | None) -> list[str]:
        visible = await self._knowledge.visible_collections(agent)
        if collection is None:
            return visible
        if collection not in visible:
            raise CollectionNotFound(collection)
        return [collection]

    async def _literal(
        self,
        query: str,
        agent: str | None,
        collections: Sequence[str],
        top_k: int,
    ) -> SearchOutcome:
        """ripgrep over ``collections``, folded from line matches into file hits.

        The agent is passed through rather than dropped, so the search reads
        exactly the collections its caller may see — never a wider set.
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
                    excerpt=tuple(matched[:_EXCERPT_LINES]),
                )
            )
        return SearchOutcome(hits=tuple(hits))
