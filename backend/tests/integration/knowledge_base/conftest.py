"""Fixtures for KB application-layer integration tests.

Wires the full real stack — real SQLite (unified ``documents``/``chunks``/FTS5),
real filesystem under ``tmp_path``, real ``ConverterRegistry`` + ripgrep — with a
deterministic fake embedder so vector paths are exercised without a provider SDK.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

import coffer.infrastructure.knowledge  # noqa: F401 — register ORM + FTS5 DDL
from coffer.application.audit_service import AuditService
from coffer.application.knowledge.reindex import Reindexer
from coffer.application.knowledge.retrieval import KnowledgeRetrieval
from coffer.application.knowledge_base.kind import make_kb_kind
from coffer.application.knowledge_base.service import KnowledgeBaseService
from coffer.application.resource_service import ResourceService
from coffer.domain.knowledge.embedder import EmbeddingConfig
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.converters.registry import default_registry
from coffer.infrastructure.knowledge.grep import RipgrepGrep
from coffer.infrastructure.knowledge.repository import DocumentRepo
from coffer.infrastructure.knowledge.sqlite_index import SqliteKnowledgeIndex
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)


class FakeEmbedder:
    """Deterministic bag-of-chars embedder (no network, no SDK)."""

    def __init__(self, dimensions: int) -> None:
        self._dim = dimensions

    @property
    def dimensions(self) -> int:
        return self._dim

    async def embed(self, texts):  # type: ignore[no-untyped-def]
        out = []
        for t in texts:
            vec = [0.0] * self._dim
            for ch in t:
                vec[ord(ch) % self._dim] += 1.0
            out.append(vec)
        return out


def fake_embedder_factory(config: EmbeddingConfig) -> FakeEmbedder:
    return FakeEmbedder(config.dimensions)


class FakeVecIndex:
    """In-memory vector index (stands in for sqlite-vec in tests)."""

    def __init__(self) -> None:
        self._rows: dict[str, list[float]] = {}
        self.dropped = False

    def available(self) -> bool:
        return True

    async def upsert(self, rows) -> None:  # type: ignore[no-untyped-def]
        for chunk_id, vector in rows:
            self._rows[chunk_id] = list(vector)

    async def delete(self, chunk_ids) -> None:  # type: ignore[no-untyped-def]
        for cid in chunk_ids:
            self._rows.pop(cid, None)

    async def drop(self) -> None:
        self._rows.clear()
        self.dropped = True

    async def knn(self, vector, top_k):  # type: ignore[no-untyped-def]
        def _dist(v: list[float]) -> float:
            return sum((a - b) ** 2 for a, b in zip(vector, v, strict=False))

        ranked = sorted(((cid, _dist(v)) for cid, v in self._rows.items()), key=lambda r: r[1])
        return ranked[:top_k]


@dataclass
class KBHarness:
    service: KnowledgeBaseService
    resources: ResourceService
    documents: DocumentRepo
    audit: AuditService
    sm: async_sessionmaker  # type: ignore[type-arg]
    vec_stores: dict[tuple[str, str], FakeVecIndex]

    async def create_kb(self, name: str, *, config: dict | None = None) -> None:
        await self.resources.register(
            kind="knowledge_base",
            name=name,
            config=config or {},
            actor="user",
        )


@pytest_asyncio.fixture
async def kb(tmp_path: pathlib.Path, monkeypatch):
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    db_path = tmp_path / "c.db"
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)

    documents = DocumentRepo(sm)
    audit = AuditService(SqlAlchemyAuditRepo(sm))

    vec_stores: dict[tuple[str, str], FakeVecIndex] = {}

    def index_factory(kind: str, resource_name: str, *, dimensions):  # type: ignore[no-untyped-def]
        # Mirrors production wiring: the vec index is ALWAYS attached so delete
        # paths (which know no embedding width) reach the vector rows too.
        vec = vec_stores.setdefault((kind, resource_name), FakeVecIndex())
        return SqliteKnowledgeIndex(sm, kind=kind, resource_name=resource_name, vec=vec)

    retrieval = KnowledgeRetrieval(
        index_factory=index_factory,
        grep=RipgrepGrep(),
        embedder_factory=fake_embedder_factory,
    )
    reindexer = Reindexer(embedder_factory=fake_embedder_factory)

    service = KnowledgeBaseService(
        resource_service=None,  # set below (circular: kind needs service)
        documents=documents,
        converters=default_registry(),
        retrieval=retrieval,
        reindexer=reindexer,
        audit=audit,
        paths=paths,
    )
    kinds = {"knowledge_base": make_kb_kind(service)}
    resources = ResourceService(kinds, SqlAlchemyResourceRepo(sm), audit)
    service._resources = resources  # type: ignore[attr-defined]

    try:
        yield KBHarness(
            service=service,
            resources=resources,
            documents=documents,
            audit=audit,
            sm=sm,
            vec_stores=vec_stores,
        )
    finally:
        await engine.dispose()


@pytest.fixture
def vector_config() -> dict:
    return {
        "enabled_modes": ["keyword", "grep", "vector"],
        "default_mode": "keyword",
        "embedding": {
            "provider": "local",
            "model": "fake-model",
            "dimensions": 32,
        },
    }
