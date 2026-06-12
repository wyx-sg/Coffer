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

import hashlib
from collections.abc import Sequence

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.domain.knowledge.retrieval import Passage
from coffer.infrastructure.knowledge.models import ChunkModel
from coffer.infrastructure.knowledge.vec_index import VecIndex


def store_scope(kind: str, resource_name: str) -> str:
    """12-hex digest namespacing chunk ids per ``(kind, resource_name)`` store.

    Document ids are content-addressed, so the same file ingested into two
    stores repeats its document id; a bare ``<doc-id>:<position>`` chunk id
    would collide across stores (``chunks.id`` is the PK and ``documents_fts``
    has no ``kind`` column), letting the second store steal the first store's
    chunk + FTS rows. The digest prefix keeps chunk ids globally unique. Keep
    in sync with migration 0017, which rekeys pre-existing rows.
    """
    return hashlib.sha1(f"{kind}\x00{resource_name}".encode()).hexdigest()[:12]


class SqliteKnowledgeIndex:
    """chunk + FTS5 (+ optional vec) index over the unified tables.

    Chunk/FTS rows are keyed ``'<store-scope>:<doc-id>:<position>'`` (globally
    unique, see ``store_scope``). The sqlite-vec rows keep the bare
    ``'<doc-id>:<position>'`` id: the vec table is already per-store (named by
    kind + resource), so bare ids are unambiguous there and existing vec rows
    survive the 0017 rekey without a rebuild.
    """

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
        self._scope = store_scope(kind, resource_name)
        self._vec = vec

    def _chunk_id(self, document_id: str, position: int) -> str:
        return f"{self._scope}:{document_id}:{position}"

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
        # vanish mid-replace. Everything is scoped to THIS store: the same
        # document_id may live in other stores (content-addressed ids).
        async with self._sm() as session:
            old = (
                await session.execute(
                    text(
                        "SELECT id, position FROM chunks WHERE document_id = :d "
                        "AND kind = :kind AND resource_name = :rn"
                    ),
                    {"d": document_id, "kind": self._kind, "rn": self._resource},
                )
            ).all()
            old_ids = [str(r.id) for r in old]
            if old_ids:
                await session.execute(
                    text("DELETE FROM documents_fts WHERE chunk_id IN :ids").bindparams(
                        bindparam("ids", expanding=True)
                    ),
                    {"ids": old_ids},
                )
                await session.execute(
                    text(
                        "DELETE FROM chunks WHERE document_id = :d "
                        "AND kind = :kind AND resource_name = :rn"
                    ),
                    {"d": document_id, "kind": self._kind, "rn": self._resource},
                )
            for position, chunk in enumerate(chunks):
                chunk_id = self._chunk_id(document_id, position)
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
        # Vec rows keep the bare '<doc-id>:<position>' id (per-store table).
        old_vec_ids = [f"{document_id}:{int(r.position)}" for r in old]
        if self._vec is not None and old_vec_ids:
            if vectors is None:
                # No fresh vectors for the new text: stale embeddings must not
                # survive a re-chunk (they'd describe the OLD content).
                await self._vec.delete(old_vec_ids)
            else:
                # The upsert below overwrites surviving ids; only remove extras
                # (e.g. the chunk count shrank).
                new_ids = {f"{document_id}:{p}" for p in range(len(chunks))}
                await self._vec.delete([cid for cid in old_vec_ids if cid not in new_ids])
        if vectors is not None and self._vec is not None and self._vec.available():
            rows = [
                (f"{document_id}:{position}", vector) for position, vector in enumerate(vectors)
            ]
            await self._vec.upsert(rows)
        return len(chunks)

    async def delete_chunks(self, document_id: str) -> None:
        # Scoped to THIS store: the same document_id may live in other stores
        # (content-addressed ids); deleting here must not wipe theirs.
        async with self._sm() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT id, position FROM chunks WHERE document_id = :d "
                        "AND kind = :kind AND resource_name = :rn"
                    ),
                    {"d": document_id, "kind": self._kind, "rn": self._resource},
                )
            ).all()
            ids = [str(r.id) for r in rows]
            if ids:
                await session.execute(
                    text("DELETE FROM documents_fts WHERE chunk_id IN :ids").bindparams(
                        bindparam("ids", expanding=True)
                    ),
                    {"ids": ids},
                )
                await session.execute(
                    text(
                        "DELETE FROM chunks WHERE document_id = :d "
                        "AND kind = :kind AND resource_name = :rn"
                    ),
                    {"d": document_id, "kind": self._kind, "rn": self._resource},
                )
                await session.commit()
        if self._vec is not None and rows:
            # Vec rows keep the bare '<doc-id>:<position>' id (per-store table).
            await self._vec.delete([f"{document_id}:{int(r.position)}" for r in rows])

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
        # KNN ids are the bare '<doc-id>:<position>' (per-store vec table);
        # chunk/FTS rows are keyed by the store-scoped id.
        order = {cid: rank for rank, (cid, _dist) in enumerate(knn)}
        ids = [f"{self._scope}:{cid}" for cid in order]
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
                # smaller distance ⇒ higher score (dist is keyed by bare ids)
                score=1.0 / (1.0 + float(dist.get(f"{r.document_id}:{r.position}", 0.0))),
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
