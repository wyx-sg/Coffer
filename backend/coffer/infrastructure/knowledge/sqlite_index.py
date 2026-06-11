"""The ``KnowledgeIndex`` implementation: ``chunks`` + ``documents_fts`` (FTS5
keyword/bm25) + optional ``vec_chunks`` (delegated to ``VecIndex``).

FTS5 is bundled with SQLite, so keyword writes/reads go through the async
SQLAlchemy session. The ``documents_fts`` table stores the chunk text once
inside the FTS index (not duplicated into a base table); the ``chunk_id``
UNINDEXED column maps a keyword hit back to its ``chunks`` row.

sqlite-vec lives in ``vec_index.py``; this module only calls it (and only when a
``VecIndex`` is supplied and available), so a missing native extension degrades
to keyword without touching this code path.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.domain.knowledge.retrieval import Passage
from coffer.infrastructure.knowledge.models import ChunkModel
from coffer.infrastructure.knowledge.vec_index import VecIndex


class SqliteKnowledgeIndex:
    """chunk + FTS5 (+ optional vec) index over the unified tables."""

    def __init__(
        self,
        sm: async_sessionmaker,  # type: ignore[type-arg]
        *,
        kind: str,
        resource_name: str,
        vec: VecIndex | None = None,
    ) -> None:
        self._sm = sm
        self._kind = kind
        self._resource = resource_name
        self._vec = vec

    # --- writes -------------------------------------------------------------

    async def upsert_chunks(
        self,
        document_id: str,
        chunks: Sequence[str],
        vectors: Sequence[Sequence[float]] | None,
    ) -> int:
        # Delete + insert in ONE transaction: a two-commit replace would let a
        # concurrent upsert interleave between them (PK IntegrityError /
        # duplicated FTS rows) and let a concurrent search see the document
        # vanish mid-replace.
        async with self._sm() as session:
            old_ids = [
                r[0]
                for r in (
                    await session.execute(
                        text("SELECT id FROM chunks WHERE document_id = :d"),
                        {"d": document_id},
                    )
                ).all()
            ]
            if old_ids:
                await session.execute(
                    text("DELETE FROM documents_fts WHERE chunk_id IN :ids").bindparams(
                        bindparam("ids", expanding=True)
                    ),
                    {"ids": old_ids},
                )
                await session.execute(
                    text("DELETE FROM chunks WHERE document_id = :d"),
                    {"d": document_id},
                )
            for position, chunk in enumerate(chunks):
                chunk_id = f"{document_id}:{position}"
                session.add(
                    ChunkModel(
                        id=chunk_id,
                        document_id=document_id,
                        kind=self._kind,
                        resource_name=self._resource,
                        position=position,
                    )
                )
                await session.execute(
                    text(
                        "INSERT INTO documents_fts(text, resource_name, chunk_id) "
                        "VALUES (:text, :rn, :cid)"
                    ),
                    {"text": chunk, "rn": self._resource, "cid": chunk_id},
                )
            await session.commit()
        if self._vec is not None and old_ids:
            if vectors is None:
                # No fresh vectors for the new text: stale embeddings must not
                # survive a re-chunk (they'd describe the OLD content).
                await self._vec.delete(old_ids)
            else:
                # The upsert below overwrites surviving ids; only remove extras
                # (e.g. the chunk count shrank).
                new_ids = {f"{document_id}:{p}" for p in range(len(chunks))}
                await self._vec.delete([cid for cid in old_ids if cid not in new_ids])
        if vectors is not None and self._vec is not None and self._vec.available():
            rows = [
                (f"{document_id}:{position}", vector) for position, vector in enumerate(vectors)
            ]
            await self._vec.upsert(rows)
        return len(chunks)

    async def delete_chunks(self, document_id: str) -> None:
        async with self._sm() as session:
            ids = [
                r[0]
                for r in (
                    await session.execute(
                        text("SELECT id FROM chunks WHERE document_id = :d"),
                        {"d": document_id},
                    )
                ).all()
            ]
            if ids:
                await session.execute(
                    text("DELETE FROM documents_fts WHERE chunk_id IN :ids").bindparams(
                        bindparam("ids", expanding=True)
                    ),
                    {"ids": ids},
                )
                await session.execute(
                    text("DELETE FROM chunks WHERE document_id = :d"),
                    {"d": document_id},
                )
                await session.commit()
        if self._vec is not None and ids:
            await self._vec.delete(ids)

    async def drop_store(self) -> None:
        """Drop this store's per-store vector table (store-level cleanup).

        Chunk/FTS rows are removed via ``delete_resource`` (SQLAlchemy) by the
        caller; this only reaches the sqlite-vec table, which lives outside the
        async session and would otherwise leak across a same-name re-create.
        """
        if self._vec is not None:
            await self._vec.drop()

    # --- reads --------------------------------------------------------------

    async def keyword_search(self, resource_name: str, query: str, top_k: int) -> Sequence[Passage]:
        match = _fts_query(query)
        if not match:
            return []
        async with self._sm() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT f.chunk_id, f.text, bm25(documents_fts) AS rank, "
                        "       c.document_id, c.position, d.title "
                        "FROM documents_fts f "
                        "JOIN chunks c ON c.id = f.chunk_id "
                        "JOIN documents d ON d.id = c.document_id "
                        "  AND d.kind = c.kind AND d.resource_name = c.resource_name "
                        "WHERE documents_fts MATCH :q AND f.resource_name = :rn "
                        # Scope by kind too: a KB and a memory store may share a
                        # resource name (UniqueConstraint is on (kind, name)).
                        "  AND c.kind = :kind "
                        "ORDER BY rank LIMIT :k"
                    ),
                    {"q": match, "rn": resource_name, "kind": self._kind, "k": top_k},
                )
            ).all()
        return [
            Passage(
                document_id=str(r.document_id),
                title=str(r.title or ""),
                text=str(r.text or ""),
                # bm25 returns a negative score (lower = better); flip so larger
                # is more relevant for the caller.
                score=-float(r.rank),
                position=int(r.position),
            )
            for r in rows
        ]

    async def vector_search(
        self, resource_name: str, vector: Sequence[float], top_k: int
    ) -> Sequence[Passage]:
        if self._vec is None or not self._vec.available():
            return []
        knn = await self._vec.knn(vector, top_k)
        if not knn:
            return []
        order = {cid: rank for rank, (cid, _dist) in enumerate(knn)}
        ids = list(order)
        async with self._sm() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT f.chunk_id, f.text, c.document_id, c.position, d.title "
                        "FROM documents_fts f "
                        "JOIN chunks c ON c.id = f.chunk_id "
                        "JOIN documents d ON d.id = c.document_id "
                        "  AND d.kind = c.kind AND d.resource_name = c.resource_name "
                        "WHERE f.chunk_id IN :ids AND f.resource_name = :rn "
                        # Scope by kind too (see keyword_search). The KNN is
                        # already per-store, but this defends against a stale
                        # chunk_id colliding across kinds.
                        "  AND c.kind = :kind"
                    ).bindparams(bindparam("ids", expanding=True)),
                    {"ids": ids, "rn": resource_name, "kind": self._kind},
                )
            ).all()
        dist = dict(knn)
        passages = [
            Passage(
                document_id=str(r.document_id),
                title=str(r.title or ""),
                text=str(r.text or ""),
                # smaller distance ⇒ higher score
                score=1.0 / (1.0 + float(dist.get(str(r.chunk_id), 0.0))),
                position=int(r.position),
            )
            for r in rows
        ]
        passages.sort(key=lambda p: order.get(f"{p.document_id}:{p.position}", 0))
        return passages


def _fts_query(query: str) -> str:
    """Turn a free-text query into a safe FTS5 MATCH expression.

    Each whitespace-separated term is double-quoted (so punctuation/operators in
    user input can't break the parser) and OR-joined.
    """
    terms = [t for t in query.split() if t.strip()]
    quoted = ['"' + t.replace('"', '""') + '"' for t in terms]
    return " OR ".join(quoted)
