"""Routes each KB to its search backend (keyword vs semantic) by config.

The application layer holds a single ``KnowledgeBaseStore``; this adapter is
that store. It remembers the ``search_mode`` declared when a KB is opened and
forwards ingest/search to the matching backend. Teardown (delete_document,
drop) fans out to BOTH backends because the service calls them without a prior
``open`` — and both backends are no-ops when they hold nothing for that KB.
"""

from __future__ import annotations

from collections.abc import Sequence

from coffer.domain.knowledge_base.config import KnowledgeBaseConfig, SearchMode
from coffer.domain.knowledge_base.document import Document
from coffer.domain.knowledge_base.store import KnowledgeBaseStore, Passage


class DispatchingKnowledgeBaseStore(KnowledgeBaseStore):
    def __init__(
        self,
        *,
        keyword: KnowledgeBaseStore,
        semantic: KnowledgeBaseStore,
    ) -> None:
        self._keyword = keyword
        self._semantic = semantic
        # kb_name -> mode, populated on open(); defaults to keyword when unknown.
        self._mode: dict[str, SearchMode] = {}

    def _backend(self, kb_name: str) -> KnowledgeBaseStore:
        return self._semantic if self._mode.get(kb_name) == "semantic" else self._keyword

    async def open(self, kb_name: str, config: KnowledgeBaseConfig) -> None:
        self._mode[kb_name] = config.search_mode
        await self._backend(kb_name).open(kb_name, config)

    async def ingest(self, kb_name: str, document: Document, text: str) -> int:
        return await self._backend(kb_name).ingest(kb_name, document, text)

    async def search(self, kb_name: str, query: str, top_k: int) -> Sequence[Passage]:
        return await self._backend(kb_name).search(kb_name, query, top_k)

    async def delete_document(self, kb_name: str, document_id: str) -> None:
        # Mode may be unknown here (service.delete_document does not open first).
        # Both backends are idempotent: each removes its own copy if present.
        await self._keyword.delete_document(kb_name, document_id)
        await self._semantic.delete_document(kb_name, document_id)

    async def drop(self, kb_name: str) -> None:
        await self._keyword.drop(kb_name)
        await self._semantic.drop(kb_name)
        self._mode.pop(kb_name, None)

    async def close(self) -> None:
        await self._keyword.close()
        await self._semantic.close()
