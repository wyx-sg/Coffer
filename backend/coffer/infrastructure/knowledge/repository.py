"""Repository for the unified ``documents`` table (KB + memory).

Document-row CRUD only; chunk / FTS5 / vec writes live in ``sqlite_index.py``.
Both faces share this repo, scoped by ``(kind, resource_name)``.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.domain.knowledge.document import Document
from coffer.infrastructure.knowledge.models import ChunkModel, DocumentModel


def _tz(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _to_domain(row: DocumentModel) -> Document:
    return Document(
        id=row.id,
        kind=row.kind,
        resource_name=row.resource_name,
        project_id=row.project_id,
        path=row.path,
        title=row.title,
        description=row.description,
        content_sha256=row.content_sha256,
        source_mode=row.source_mode,
        metadata=json.loads(row.metadata_json or "{}"),
        created_at=_tz(row.created_at),
        updated_at=_tz(row.updated_at),
    )


class DocumentRepo:
    """Implements the document-row half of the data-model's repo surface."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def upsert_document(self, d: Document) -> Document:
        async with self._sm() as session:
            stmt = select(DocumentModel).where(
                DocumentModel.kind == d.kind,
                DocumentModel.resource_name == d.resource_name,
                DocumentModel.id == d.id,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            payload = json.dumps(d.metadata, ensure_ascii=False, sort_keys=True)
            if row is None:
                row = DocumentModel(
                    id=d.id,
                    kind=d.kind,
                    resource_name=d.resource_name,
                    project_id=d.project_id,
                    path=d.path,
                    title=d.title,
                    description=d.description,
                    metadata_json=payload,
                    content_sha256=d.content_sha256,
                    source_mode=d.source_mode,
                    created_at=d.created_at,
                    updated_at=d.updated_at,
                )
                session.add(row)
            else:
                row.path = d.path
                row.project_id = d.project_id
                row.title = d.title
                row.description = d.description
                row.metadata_json = payload
                row.content_sha256 = d.content_sha256
                row.source_mode = d.source_mode
                row.updated_at = d.updated_at
            await session.commit()
            await session.refresh(row)
            return _to_domain(row)

    async def get_document(self, kind: str, resource_name: str, doc_id: str) -> Document | None:
        async with self._sm() as session:
            stmt = select(DocumentModel).where(
                DocumentModel.kind == kind,
                DocumentModel.resource_name == resource_name,
                DocumentModel.id == doc_id,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return _to_domain(row) if row else None

    async def list_documents(
        self, kind: str, resource_name: str, *, limit: int = 50, offset: int = 0
    ) -> list[Document]:
        async with self._sm() as session:
            stmt = (
                select(DocumentModel)
                .where(
                    DocumentModel.kind == kind,
                    DocumentModel.resource_name == resource_name,
                )
                .order_by(DocumentModel.updated_at.desc(), DocumentModel.id)
                .limit(limit)
                .offset(offset)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [_to_domain(r) for r in rows]

    async def count_documents(self, kind: str, resource_name: str) -> int:
        async with self._sm() as session:
            stmt = (
                select(func.count())
                .select_from(DocumentModel)
                .where(
                    DocumentModel.kind == kind,
                    DocumentModel.resource_name == resource_name,
                )
            )
            return int((await session.execute(stmt)).scalar_one())

    async def count_chunks(self, kind: str, resource_name: str) -> int:
        """Total chunk rows for a store (used by KB / memory metrics)."""
        async with self._sm() as session:
            stmt = (
                select(func.count())
                .select_from(ChunkModel)
                .where(
                    ChunkModel.kind == kind,
                    ChunkModel.resource_name == resource_name,
                )
            )
            return int((await session.execute(stmt)).scalar_one())

    async def exists_source(self, kind: str, resource_name: str, source_sha256: str) -> bool:
        """KB dedup: is there a row whose ``metadata->>'source_sha256'`` matches?

        Enforced in the repo (not a SQL unique index) because memory rows have
        no source file.
        """
        async with self._sm() as session:
            stmt = select(DocumentModel.id).where(
                DocumentModel.kind == kind,
                DocumentModel.resource_name == resource_name,
                text("json_extract(documents.metadata, '$.source_sha256') = :sha"),
            )
            result = await session.execute(stmt, {"sha": source_sha256})
            return result.first() is not None

    async def delete_document(self, kind: str, resource_name: str, doc_id: str) -> bool:
        async with self._sm() as session:
            stmt = sa_delete(DocumentModel).where(
                DocumentModel.kind == kind,
                DocumentModel.resource_name == resource_name,
                DocumentModel.id == doc_id,
            )
            result = await session.execute(stmt)
            await session.commit()
            return (result.rowcount or 0) > 0

    async def delete_resource(self, kind: str, resource_name: str) -> int:
        async with self._sm() as session:
            stmt = sa_delete(DocumentModel).where(
                DocumentModel.kind == kind,
                DocumentModel.resource_name == resource_name,
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount or 0

    async def all_document_ids(self, kind: str, resource_name: str) -> Sequence[str]:
        async with self._sm() as session:
            stmt = select(DocumentModel.id).where(
                DocumentModel.kind == kind,
                DocumentModel.resource_name == resource_name,
            )
            return [r[0] for r in (await session.execute(stmt)).all()]
