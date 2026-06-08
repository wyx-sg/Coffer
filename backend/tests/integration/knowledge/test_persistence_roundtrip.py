"""Integration: unified documents repo roundtrip over real SQLite."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.domain.knowledge.document import (
    KIND_KNOWLEDGE_BASE,
    KIND_MEMORY,
    WORKSPACE_GLOBAL_PROJECT_ID,
    Document,
)


def _doc(doc_id: str, kind: str, resource: str, *, source_sha: str | None = None) -> Document:
    now = datetime.now(UTC)
    meta: dict[str, object] = {}
    if source_sha:
        meta["source_sha256"] = source_sha
    return Document(
        id=doc_id,
        kind=kind,
        resource_name=resource,
        project_id=WORKSPACE_GLOBAL_PROJECT_ID,
        path=f"docs/{doc_id}.md",
        title=f"Title {doc_id}",
        content_sha256="abc",
        source_mode="converted",
        created_at=now,
        updated_at=now,
        metadata=meta,
    )


@pytest.mark.asyncio
async def test_create_get_list_count(substrate) -> None:
    repo = substrate.repo
    await repo.upsert_document(_doc("aaaa", KIND_KNOWLEDGE_BASE, "kb1"))
    await repo.upsert_document(_doc("bbbb", KIND_KNOWLEDGE_BASE, "kb1"))
    got = await repo.get_document(KIND_KNOWLEDGE_BASE, "kb1", "aaaa")
    assert got is not None and got.title == "Title aaaa"
    docs = await repo.list_documents(KIND_KNOWLEDGE_BASE, "kb1")
    assert {d.id for d in docs} == {"aaaa", "bbbb"}
    assert await repo.count_documents(KIND_KNOWLEDGE_BASE, "kb1") == 2


@pytest.mark.asyncio
async def test_upsert_updates_existing(substrate) -> None:
    repo = substrate.repo
    d = _doc("aaaa", KIND_KNOWLEDGE_BASE, "kb1")
    await repo.upsert_document(d)
    edited = Document(**{**d.__dict__, "title": "New Title", "source_mode": "edited"})
    await repo.upsert_document(edited)
    got = await repo.get_document(KIND_KNOWLEDGE_BASE, "kb1", "aaaa")
    assert got is not None
    assert got.title == "New Title"
    assert got.source_mode == "edited"
    assert await repo.count_documents(KIND_KNOWLEDGE_BASE, "kb1") == 1


@pytest.mark.asyncio
async def test_exists_source_dedup(substrate) -> None:
    repo = substrate.repo
    await repo.upsert_document(_doc("aaaa", KIND_KNOWLEDGE_BASE, "kb1", source_sha="deadbeef"))
    assert await repo.exists_source(KIND_KNOWLEDGE_BASE, "kb1", "deadbeef") is True
    assert await repo.exists_source(KIND_KNOWLEDGE_BASE, "kb1", "other") is False


@pytest.mark.asyncio
async def test_kind_isolation_same_id(substrate) -> None:
    """Same content-addressed id may appear under both faces (composite PK)."""
    repo = substrate.repo
    await repo.upsert_document(_doc("shared01", KIND_KNOWLEDGE_BASE, "kb1"))
    await repo.upsert_document(_doc("shared01", KIND_MEMORY, "global"))
    assert await repo.get_document(KIND_KNOWLEDGE_BASE, "kb1", "shared01") is not None
    assert await repo.get_document(KIND_MEMORY, "global", "shared01") is not None


@pytest.mark.asyncio
async def test_delete_document_and_resource(substrate) -> None:
    repo = substrate.repo
    await repo.upsert_document(_doc("aaaa", KIND_KNOWLEDGE_BASE, "kb1"))
    await repo.upsert_document(_doc("bbbb", KIND_KNOWLEDGE_BASE, "kb1"))
    assert await repo.delete_document(KIND_KNOWLEDGE_BASE, "kb1", "aaaa") is True
    assert await repo.delete_document(KIND_KNOWLEDGE_BASE, "kb1", "aaaa") is False
    removed = await repo.delete_resource(KIND_KNOWLEDGE_BASE, "kb1")
    assert removed == 1
    assert await repo.count_documents(KIND_KNOWLEDGE_BASE, "kb1") == 0
