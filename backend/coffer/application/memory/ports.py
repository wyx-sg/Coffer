"""Ports the memory application layer depends on.

The document-row repo used by the memory face is structurally the substrate
``infrastructure.knowledge.repository.DocumentRepo``; declaring it as a Protocol
here lets the service + reconciler be typed and faked without importing the
concrete repo.
"""

from __future__ import annotations

from typing import Protocol

from coffer.domain.knowledge.document import Document


class MemoryDocumentRepo(Protocol):
    async def upsert_document(self, d: Document) -> Document: ...
    async def get_document(self, kind: str, resource_name: str, doc_id: str) -> Document | None: ...
    async def list_documents(
        self, kind: str, resource_name: str, *, limit: int, offset: int
    ) -> list[Document]: ...
    async def count_documents(self, kind: str, resource_name: str) -> int: ...
    async def count_chunks(self, kind: str, resource_name: str) -> int: ...
    async def delete_document(self, kind: str, resource_name: str, doc_id: str) -> bool: ...
    async def delete_resource(self, kind: str, resource_name: str) -> int: ...
