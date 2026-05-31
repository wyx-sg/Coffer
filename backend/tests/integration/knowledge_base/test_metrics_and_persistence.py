"""Tests for KB metrics, doc-text retrieval, and the persistence of state
across simulated daemon restarts."""

from __future__ import annotations

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.knowledge_base.kind import make_kb_kind
from coffer.application.knowledge_base.service import KnowledgeBaseService
from coffer.application.resource_service import ResourceService
from coffer.domain.knowledge_base.config import KnowledgeBaseConfig
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


async def _services(tmp_path, monkeypatch):
    monkeypatch.setenv("COFFER_KB_ROOT", str(tmp_path / "kb"))
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    store = FakeKnowledgeBaseStore()
    kb_svc = KnowledgeBaseService.build(
        resource_service=None,  # type: ignore[arg-type]
        store=store,
        documents=SqlAlchemyKBDocumentRepo(sm),
        audit=audit,
        raw_dir=kb_raw_dir,
        raw_file=raw_file_path,
        kb_dir=kb_dir,
        kb_root=kb_root,
        extractor=extract_text,
    )
    rs = ResourceService(
        kinds={"knowledge_base": make_kb_kind(kb_svc)},
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
    )
    kb_svc._resources = rs  # type: ignore[attr-defined]
    return rs, kb_svc, store, engine


@pytest.mark.acceptance(
    spec="006-knowledge-base",
    scenario="KB metrics show document count and disk usage",
)
async def test_metrics(tmp_path, monkeypatch):
    rs, kb_svc, _store, engine = await _services(tmp_path, monkeypatch)
    try:
        await rs.register(
            kind="knowledge_base",
            name="kb1",
            config=KnowledgeBaseConfig().model_dump(),
            actor="cli",
        )
        await kb_svc.ingest_bytes(kb_name="kb1", filename="a.md", raw_bytes=b"alpha", actor="cli")
        count, disk = await kb_svc.metrics(kb_name="kb1")
        assert count == 1
        assert disk >= 5  # at least the raw file
    finally:
        await engine.dispose()


@pytest.mark.acceptance(
    spec="006-knowledge-base",
    scenario="agent fetches a document by id",
)
async def test_get_document_returns_text(tmp_path, monkeypatch):
    rs, kb_svc, _store, engine = await _services(tmp_path, monkeypatch)
    try:
        await rs.register(
            kind="knowledge_base",
            name="kb1",
            config=KnowledgeBaseConfig().model_dump(),
            actor="cli",
        )
        doc = await kb_svc.ingest_bytes(
            kb_name="kb1", filename="x.md", raw_bytes=b"# hello", actor="cli"
        )
        d, text = await kb_svc.get_document_text(kb_name="kb1", document_id=doc.id)
        assert d.id == doc.id
        assert "hello" in text
    finally:
        await engine.dispose()
