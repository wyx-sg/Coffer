"""Ports the knowledge application layer depends on.

Two views of the same substrate repo
(``infrastructure.knowledge.repository.DocumentRepo``), declared as Protocols so
callers can be typed and faked without importing the concrete class:

- ``KnowledgeDocumentRepo`` — the narrow surface the entry reconciler needs.
- ``DocumentRepoPort`` — the wider one the ingestion path needs (the same rows
  plus the filename and chunk lookups).
"""

from __future__ import annotations

from typing import Protocol

from coffer.domain.knowledge.document import Document


class KnowledgeDocumentRepo(Protocol):
    async def upsert_document(self, d: Document) -> Document: ...
    async def get_document(self, kind: str, resource_name: str, doc_id: str) -> Document | None: ...
    async def list_documents(
        self, kind: str, resource_name: str, *, limit: int, offset: int
    ) -> list[Document]: ...
    async def count_documents(self, kind: str, resource_name: str) -> int: ...
    async def count_chunks(self, kind: str, resource_name: str) -> int: ...
    async def delete_document(self, kind: str, resource_name: str, doc_id: str) -> bool: ...
    async def delete_resource(self, kind: str, resource_name: str) -> int: ...


class DocumentRepoPort(Protocol):
    """The document-row repo surface the ingestion path uses (a superset of
    ``KnowledgeDocumentRepo``: the same rows plus the filename/chunk lookups
    only ingestion needs)."""

    async def upsert_document(self, d: Document) -> Document: ...
    async def get_document(self, kind: str, resource_name: str, doc_id: str) -> Document | None: ...
    #: ``lane`` restricts a read to one writer's rows. Both a scope's writers
    #: index into the same table under one ``(kind, resource_name)``, so a
    #: document read that omits it also returns the entries.
    async def list_documents(
        self,
        kind: str,
        resource_name: str,
        *,
        limit: int,
        offset: int,
        q: str | None = None,
        lane: str | None = None,
    ) -> list[Document]: ...
    async def count_documents(
        self, kind: str, resource_name: str, *, q: str | None = None, lane: str | None = None
    ) -> int: ...
    async def count_pending_embeds(
        self, kind: str, resource_name: str, *, lane: str | None = None
    ) -> int: ...
    async def count_chunks(
        self, kind: str, resource_name: str, *, lane: str | None = None
    ) -> int: ...
    async def chunk_counts(
        self, kind: str, resource_name: str, *, lane: str | None = None
    ) -> dict[str, int]: ...
    async def find_by_filename(
        self, kind: str, resource_name: str, project_id: str, original_filename: str
    ) -> Document | None: ...
    async def delete_document(self, kind: str, resource_name: str, doc_id: str) -> bool: ...
    async def delete_resource(self, kind: str, resource_name: str) -> int: ...
