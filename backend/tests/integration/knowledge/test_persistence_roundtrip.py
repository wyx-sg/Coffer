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


def _doc(
    doc_id: str,
    kind: str,
    resource: str,
    *,
    source_sha: str | None = None,
    filename: str | None = None,
) -> Document:
    now = datetime.now(UTC)
    meta: dict[str, object] = {}
    if source_sha:
        meta["source_sha256"] = source_sha
    if filename:
        meta["original_filename"] = filename
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
async def test_find_by_filename_matches_in_scope(substrate) -> None:
    """ADR-028 re-upload match: a document is found by its original_filename
    within (kind, resource, project_id), the stable key for re-upload."""
    repo = substrate.repo
    await repo.upsert_document(_doc("ulid-aaaa", KIND_KNOWLEDGE_BASE, "kb1", filename="a.md"))
    found = await repo.find_by_filename(
        KIND_KNOWLEDGE_BASE, "kb1", WORKSPACE_GLOBAL_PROJECT_ID, "a.md"
    )
    assert found is not None and found.id == "ulid-aaaa"
    # A different filename, or the same filename in another KB, does not match.
    assert (
        await repo.find_by_filename(
            KIND_KNOWLEDGE_BASE, "kb1", WORKSPACE_GLOBAL_PROJECT_ID, "other.md"
        )
        is None
    )
    assert (
        await repo.find_by_filename(KIND_KNOWLEDGE_BASE, "kb2", WORKSPACE_GLOBAL_PROJECT_ID, "a.md")
        is None
    )


@pytest.mark.asyncio
async def test_set_locked_flips_and_persists(substrate) -> None:
    """ADR-028: set_locked flips the per-document lock and round-trips."""
    repo = substrate.repo
    await repo.upsert_document(_doc("ulid-lock", KIND_KNOWLEDGE_BASE, "kb1", filename="a.md"))
    locked = await repo.set_locked(KIND_KNOWLEDGE_BASE, "kb1", "ulid-lock", True)
    assert locked is not None and locked.locked is True
    assert (await repo.get_document(KIND_KNOWLEDGE_BASE, "kb1", "ulid-lock")).locked is True
    unlocked = await repo.set_locked(KIND_KNOWLEDGE_BASE, "kb1", "ulid-lock", False)
    assert unlocked is not None and unlocked.locked is False
    # Unknown id → None (no row touched).
    assert await repo.set_locked(KIND_KNOWLEDGE_BASE, "kb1", "missing", True) is None


@pytest.mark.asyncio
async def test_kind_isolation_same_id(substrate) -> None:
    """The same id string may appear under both faces (composite PK)."""
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


@pytest.mark.asyncio
async def test_delete_resource_purges_chunks_and_fts(substrate) -> None:
    """Store-level deletion must remove the store's ``chunks`` and
    ``documents_fts`` rows too, not only its ``documents`` rows — orphans are
    invisible to search (the JOIN filters them) but accumulate forever."""
    from sqlalchemy import text

    repo = substrate.repo
    await repo.upsert_document(_doc("aaaa", KIND_KNOWLEDGE_BASE, "kb1"))
    idx = substrate.index(KIND_KNOWLEDGE_BASE, "kb1")
    await idx.upsert_chunks("aaaa", ["alpha beta", "gamma"], None)
    assert await repo.count_chunks(KIND_KNOWLEDGE_BASE, "kb1") == 2

    await repo.delete_resource(KIND_KNOWLEDGE_BASE, "kb1")

    assert await repo.count_chunks(KIND_KNOWLEDGE_BASE, "kb1") == 0
    async with substrate.sm() as session:
        fts_rows = (
            await session.execute(
                text("SELECT count(*) FROM documents_fts WHERE resource_name = 'kb1'")
            )
        ).scalar_one()
    assert fts_rows == 0
