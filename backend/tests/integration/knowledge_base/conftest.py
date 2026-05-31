"""Shared fixtures for knowledge_base integration tests (TEST22-004).

Lifts the previously-duplicated `_services()` helper out of
`test_kb_lifecycle.py` into a typed dataclass + fixture so the new tests
(builtin_tools, lifecycle rollback, audit-log assertions) don't each
re-paste the same wiring.

The fixture wires a real ``ResourceService`` against an in-tree SQLite,
a ``FakeKnowledgeBaseStore`` (in-memory), and the real ``extract_text``
loader. Callers may swap the store via ``services(store=...)`` for the
disk-full / rollback / engine-unavailable cases.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine

from coffer.application.audit_service import AuditService
from coffer.application.knowledge_base.kind import make_kb_kind
from coffer.application.knowledge_base.service import KnowledgeBaseService
from coffer.application.resource_service import ResourceService
from coffer.domain.knowledge_base.store import KnowledgeBaseStore
from coffer.infrastructure.knowledge_base.loaders import extract_text
from coffer.infrastructure.knowledge_base.paths import (
    kb_dir,
    kb_raw_dir,
    kb_root,
    raw_file_path,
)
from coffer.infrastructure.knowledge_base.persistence import (
    SqlAlchemyKBDocumentRepo,
)
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from tests.integration.knowledge_base.fakes import FakeKnowledgeBaseStore


@dataclass
class KBTestBundle:
    """Typed grouping of services + supporting state for KB lifecycle tests."""

    resources: ResourceService
    kb: KnowledgeBaseService
    store: KnowledgeBaseStore
    audit: AuditService
    engine: AsyncEngine
    kb_root: pathlib.Path


async def _build(
    tmp_path: pathlib.Path,
    monkeypatch,
    *,
    store: KnowledgeBaseStore | None = None,
) -> KBTestBundle:
    monkeypatch.setenv("COFFER_KB_ROOT", str(tmp_path / "kb"))

    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)

    audit = AuditService(SqlAlchemyAuditRepo(sm))
    chosen_store: KnowledgeBaseStore = store or FakeKnowledgeBaseStore()
    doc_repo = SqlAlchemyKBDocumentRepo(sm)

    kb_service = KnowledgeBaseService.build(
        resource_service=None,  # type: ignore[arg-type]
        store=chosen_store,
        documents=doc_repo,
        audit=audit,
        raw_dir=kb_raw_dir,
        raw_file=raw_file_path,
        kb_dir=kb_dir,
        kb_root=kb_root,
        extractor=extract_text,
    )
    kb_kind = make_kb_kind(kb_service)
    kinds = {"knowledge_base": kb_kind}
    resource_svc = ResourceService(
        kinds=kinds,
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
    )
    kb_service._resources = resource_svc  # type: ignore[attr-defined]

    return KBTestBundle(
        resources=resource_svc,
        kb=kb_service,
        store=chosen_store,
        audit=audit,
        engine=engine,
        kb_root=tmp_path / "kb",
    )


@pytest_asyncio.fixture
async def kb_bundle(tmp_path, monkeypatch):
    """Default KB bundle with the in-memory ``FakeKnowledgeBaseStore``."""
    bundle = await _build(tmp_path, monkeypatch)
    try:
        yield bundle
    finally:
        await bundle.engine.dispose()


@pytest_asyncio.fixture
async def kb_bundle_factory(tmp_path, monkeypatch):
    """Factory variant for tests that need a custom store (rollback, 503 …)."""
    built: list[KBTestBundle] = []

    async def _factory(*, store: KnowledgeBaseStore | None = None) -> KBTestBundle:
        bundle = await _build(tmp_path, monkeypatch, store=store)
        built.append(bundle)
        return bundle

    try:
        yield _factory
    finally:
        for b in built:
            await b.engine.dispose()
