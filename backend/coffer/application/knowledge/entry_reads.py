"""The entry read paths of ``KnowledgeService``.

A mixin, not a second service — it lives in its own module only so
``service.py`` stays under the project's 400-line ceiling. Every attribute
declared below is supplied by ``KnowledgeService.__init__``.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

from coffer.application.knowledge import session_context
from coffer.application.knowledge.ports import DocumentRepoPort
from coffer.application.knowledge.queries import (
    find_entry_scope as _find_entry_scope_in,
)
from coffer.application.knowledge.queries import (
    list_entry_files_in_dir,
    scope_metrics,
)
from coffer.application.knowledge.scope import ScopeResolver
from coffer.application.knowledge.stores import scope_name_for
from coffer.domain.knowledge.document import KIND_KNOWLEDGE, LANE_INGEST
from coffer.domain.knowledge.entry import KnowledgeEntry
from coffer.domain.knowledge.scope import ResolvedScope
from coffer.domain.knowledge.scope_config import KnowledgeConfig
from coffer.infrastructure.knowledge_scope.files import FactFile, scan_scope_dir


class EntryReads(ABC):
    """List / fetch / count the entries in one knowledge scope."""

    # Supplied by ``KnowledgeService.__init__``.
    _documents: DocumentRepoPort
    _scope: ScopeResolver

    @abstractmethod
    async def get_config(self, scope_name: str) -> KnowledgeConfig:
        """Implemented by ``KnowledgeService``."""

    @abstractmethod
    async def _resolved_for_scope(self, scope_name: str) -> ResolvedScope:
        """Implemented by ``KnowledgeService``."""

    @abstractmethod
    async def _store_fact(self, scope_name: str, fact_id: str) -> tuple[ResolvedScope, FactFile]:
        """Implemented by ``KnowledgeService``."""

    async def list_facts(
        self, *, scope_name: str, limit: int = 50, offset: int = 0
    ) -> tuple[list[KnowledgeEntry], int]:
        files, total = await self.list_fact_files(scope_name=scope_name, limit=limit, offset=offset)
        return [ff.fact for ff in files], total

    async def list_fact_files(
        self, *, scope_name: str, limit: int = 50, offset: int = 0
    ) -> tuple[list[FactFile], int]:
        """One directory scan serving fact + path per row (no per-fact rescans)."""
        resolved = await self.resolved_scope(scope_name)
        return await asyncio.to_thread(
            list_entry_files_in_dir, resolved.store_dir, limit=limit, offset=offset
        )

    async def get_fact(self, *, scope_name: str, fact_id: str) -> KnowledgeEntry:
        return (await self._store_fact(scope_name, fact_id))[1].fact

    async def resolved_scope(self, scope_name: str) -> ResolvedScope:
        """Public ``ResolvedScope`` for an EXISTING store (validates first)."""
        await self.get_config(scope_name)
        return await self._resolved_for_scope(scope_name)

    async def get_fact_with_path(
        self, *, scope_name: str, fact_id: str
    ) -> tuple[KnowledgeEntry, str]:
        """A fact plus the absolute path of its canonical markdown file."""
        _resolved, ff = await self._store_fact(scope_name, fact_id)
        return ff.fact, str(ff.path)

    async def find_entry_scope(self, *, cwd: str | None, fact_id: str) -> str:
        """Return the scope name holding ``fact_id`` across the recall scopes
        (project then global); raises ``MemoryNotFound`` if absent everywhere."""
        scopes = await self._scope.resolve_recall_scopes(cwd=cwd)
        return await asyncio.to_thread(_find_entry_scope_in, scopes, fact_id, scope_name_for)

    async def fact_count(self, *, scope_name: str) -> int:
        """Knowledge-lane fact count."""
        sd = (await self._resolved_for_scope(scope_name)).store_dir
        return len((await asyncio.to_thread(scan_scope_dir, sd)).files)

    async def metrics(self, *, scope_name: str) -> dict[str, object]:
        """One scope's numbers: entries, ingested documents, disk, modes."""
        config = await self.get_config(scope_name)
        resolved = await self._resolved_for_scope(scope_name)
        stats = await scope_metrics(resolved.store_dir, config)
        # Entries and ingested documents share one table under one
        # ``(kind, scope)``, so every document number is lane-scoped or it
        # silently counts the entries too.
        stats["document_count"] = await self._documents.count_documents(
            KIND_KNOWLEDGE, scope_name, lane=LANE_INGEST
        )
        stats["chunk_count"] = await self._documents.count_chunks(
            KIND_KNOWLEDGE, scope_name, lane=LANE_INGEST
        )
        stats["documents_degraded"] = await self._documents.count_pending_embeds(
            KIND_KNOWLEDGE, scope_name, lane=LANE_INGEST
        )
        return stats

    async def get_rules(self, *, scope_name: str) -> str | None:
        """Return the rules/rules.md text, or ``None`` if no rules exist yet."""
        return await session_context.get_rules(
            scope_name=scope_name, resolved_scope=self.resolved_scope
        )
