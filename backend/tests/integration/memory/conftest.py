"""Fixtures for memory application-layer integration tests.

Full real stack: real SQLite (unified ``documents``/``chunks``/FTS5), real
per-fact files under ``tmp_path``, real ripgrep. The scope resolver is wired
with a fake git-root resolver so a ``tmp_path`` checkout resolves to a project
store without an actual ``.git`` (a separate test covers the real git walk).
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

import pytest_asyncio

import coffer.infrastructure.knowledge  # noqa: F401 — register ORM + FTS5 DDL
from coffer.application.audit_service import AuditService
from coffer.application.knowledge.reindex import Reindexer
from coffer.application.knowledge.retrieval import KnowledgeRetrieval
from coffer.application.memory.kind import make_memory_kind
from coffer.application.memory.scope import ScopeResolver
from coffer.application.memory.service import MemoryService
from coffer.application.memory.sync import MemoryReconciler
from coffer.application.resource_service import ResourceService
from coffer.domain.knowledge.embedder import EmbeddingConfig
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.grep import RipgrepGrep
from coffer.infrastructure.knowledge.repository import DocumentRepo
from coffer.infrastructure.knowledge.sqlite_index import SqliteKnowledgeIndex
from coffer.infrastructure.memory.scope_fs import project_ulid
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


def _embedder_factory(config: EmbeddingConfig) -> FakeEmbedder:
    return FakeEmbedder(config.dimensions)


@dataclass
class MemHarness:
    service: MemoryService
    resources: ResourceService
    documents: DocumentRepo
    audit: AuditService
    project_cwd: str  # a cwd the fake git-root resolves as a project
    vec_stores: dict[tuple[str, str], FakeVecIndex] | None = None


@pytest_asyncio.fixture
async def mem(tmp_path: pathlib.Path, monkeypatch):
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(tmp_path / "memory"))
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
        embedder_factory=_embedder_factory,
    )
    reindexer = Reindexer(embedder_factory=_embedder_factory)
    reconciler = MemoryReconciler(documents=documents, retrieval=retrieval, reindexer=reindexer)

    # The "project" cwd: a fake git-root resolver that treats any path under
    # ``project_root`` as a project; everything else has no git-root.
    project_root = tmp_path / "repo"
    project_root.mkdir()

    def fake_git_root(cwd: str):  # type: ignore[no-untyped-def]
        p = pathlib.Path(cwd)
        return project_root if str(p).startswith(str(project_root)) else None

    resources = ResourceService({}, SqlAlchemyResourceRepo(sm), audit)
    scope = ScopeResolver(
        resources=resources,
        git_root=fake_git_root,
        project_ulid=project_ulid,
        store_dir=paths.memory_store_dir,
    )
    service = MemoryService(
        resource_service=resources,
        documents=documents,
        scope_resolver=scope,
        reconciler=reconciler,
        retrieval=retrieval,
        audit=audit,
        store_dir=paths.memory_store_dir,
        fact_path=paths.fact_path,
    )
    # Register the memory kind so auto-provision (resources.register) works.
    resources._kinds["memory"] = make_memory_kind(service)  # type: ignore[attr-defined]

    try:
        yield MemHarness(
            service=service,
            resources=resources,
            documents=documents,
            audit=audit,
            project_cwd=str(project_root / "src"),
            vec_stores=vec_stores,
        )
    finally:
        await engine.dispose()
