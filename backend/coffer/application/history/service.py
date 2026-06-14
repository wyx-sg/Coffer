"""HistoryService — the cross-agent transcript history (ADR-022).

A local-only, rebuildable index over the in-place agent ``.jsonl`` transcripts
the distill slice already reads. It reuses the shared knowledge substrate (the
``documents`` / FTS5 table, ADR-012) under the index-only ``transcript``
discriminator — NOT a new resource kind, never written to files-as-truth, never
synced. Search is BM25 over scrubbed natural-language turns; browse re-reads the
source file read-only.

Layering: application MAY import infrastructure/application.knowledge (the shared
substrate), exactly as the memory reconciler does. The transcript reader and the
agent catalog are injected as ports so this stays engine-free and unit-testable.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from coffer.application.history.ports import (
    AgentCatalogPort,
    DocumentStorePort,
    TranscriptReaderPort,
)
from coffer.application.knowledge.reindex import Chunker, Reindexer
from coffer.application.knowledge.retrieval import KnowledgeRetrieval
from coffer.domain.distill.locations import UnsupportedAgentTypeError
from coffer.domain.distill.session import TranscriptSession
from coffer.domain.history.results import (
    HistorySearchHit,
    HistorySessionDetail,
    HistorySessionRef,
    HistoryTurn,
    RebuildStats,
)
from coffer.domain.knowledge.document import (
    KIND_TRANSCRIPT,
    WORKSPACE_GLOBAL_PROJECT_ID,
    Document,
)
from coffer.domain.knowledge.retrieval import StoreRef

_logger = logging.getLogger(__name__)

#: Single local store name for the whole transcript history.
RESOURCE_NAME = "transcripts"
#: Snippet length surfaced per search hit.
_SNIPPET_CHARS = 280


def _const_chunker(turns: list[str]) -> Chunker:
    """A chunker that ignores its markdown and returns one chunk per turn.

    The joined markdown still drives the ``content_sha256`` no-op gate; the
    chunks are the individual scrubbed turns so a search hit maps to a turn.
    """

    def chunk(_markdown: str) -> list[str]:
        return list(turns)

    return chunk


class HistoryService:
    """Indexes, searches, and browses cross-agent transcript history."""

    def __init__(
        self,
        *,
        reader: TranscriptReaderPort,
        catalog: AgentCatalogPort,
        documents: DocumentStorePort,
        retrieval: KnowledgeRetrieval,
        reindexer: Reindexer,
    ) -> None:
        self._reader = reader
        self._catalog = catalog
        self._documents = documents
        self._retrieval = retrieval
        self._reindexer = reindexer
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    async def rebuild(self, *, agent_name: str | None = None) -> RebuildStats:
        """(Re)index transcripts for one agent, or every agent when None.

        Idempotent: unchanged sessions are skipped by ``content_sha256``; stale
        sessions (deleted on disk) are pruned for the agent types rebuilt.
        """
        async with self._lock:
            names = [agent_name] if agent_name else await self._catalog.list_agents()
            store = self._store()
            index = self._retrieval.index_for(store, dimensions=None)
            known = {d.id: d for d in await self._list_docs()}

            seen: set[str] = set()
            rebuilt_types: set[str] = set()
            indexed = unchanged = 0

            for name in names:
                try:
                    agent_type, config_dir = await self._catalog.resolve(name)
                except Exception:
                    _logger.warning("history.rebuild.resolve_failed", extra={"agent": name})
                    continue
                try:
                    sessions = await asyncio.to_thread(
                        self._reader.list_sessions,
                        agent_type_value=agent_type,
                        config_dir=config_dir,
                    )
                except UnsupportedAgentTypeError:
                    continue  # agent type has no transcripts (e.g. not claude_code/codex)
                rebuilt_types.add(agent_type)

                for session in sessions:
                    doc_id = self._doc_id(session.agent_type_value, session.session_id)
                    seen.add(doc_id)
                    turns = [m.text for m in session.messages if m.text.strip()]
                    if not turns:
                        continue
                    markdown = "\n\n".join(turns)
                    existing = known.get(doc_id)
                    outcome = await self._reindexer.reindex(
                        index=index,
                        markdown=markdown,
                        previous_sha=existing.content_sha256 if existing else None,
                        embedding=None,
                        doc_id=doc_id,
                        chunker=_const_chunker(turns),
                    )
                    if not outcome.changed:
                        unchanged += 1
                        continue
                    await self._documents.upsert_document(
                        self._session_to_document(session, content_sha256=outcome.content_sha256)
                    )
                    indexed += 1

            removed = 0
            for doc_id, doc in known.items():
                if doc_id in seen:
                    continue
                if str(doc.metadata.get("agent_type")) not in rebuilt_types:
                    continue  # only prune the agent types we just rebuilt
                await index.delete_chunks(doc_id)
                await self._documents.delete_document(KIND_TRANSCRIPT, RESOURCE_NAME, doc_id)
                removed += 1

            return RebuildStats(indexed=indexed, unchanged=unchanged, removed=removed)

    async def reset(self) -> int:
        """Drop the entire local index. Loses nothing durable — rebuildable."""
        async with self._lock:
            store = self._store()
            await self._retrieval.drop_store(store, dimensions=None)
            return await self._documents.delete_resource(KIND_TRANSCRIPT, RESOURCE_NAME)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        *,
        agent_type: str | None = None,
        project_path: str | None = None,
        limit: int = 20,
    ) -> list[HistorySearchHit]:
        """BM25 search across all indexed transcripts, optionally filtered."""
        query = query.strip()
        if not query:
            return []
        store = self._store()
        # Over-fetch so post-filtering by agent/project can still fill ``limit``.
        result = await self._retrieval.search(
            store, query, mode="keyword", top_k=max(limit * 4, limit)
        )
        hits: list[HistorySearchHit] = []
        for passage in result.passages:
            doc = await self._documents.get_document(
                KIND_TRANSCRIPT, RESOURCE_NAME, passage.document_id
            )
            if doc is None:
                continue
            meta = doc.metadata
            doc_agent_type = str(meta.get("agent_type", ""))
            if agent_type is not None and doc_agent_type != agent_type:
                continue
            doc_project = meta.get("project_path")
            if project_path is not None and doc_project != project_path:
                continue
            hits.append(
                HistorySearchHit(
                    agent_type=doc_agent_type,
                    session_id=str(meta.get("session_id", "")),
                    project_path=doc_project if isinstance(doc_project, str) else None,
                    started_at=_parse_iso(meta.get("started_at")),
                    title=doc.title,
                    snippet=passage.text[:_SNIPPET_CHARS],
                    score=passage.score,
                )
            )
            if len(hits) >= limit:
                break
        return hits

    async def list_sessions(self, *, agent_name: str) -> list[HistorySessionRef]:
        """List one agent's transcript sessions (read-only, off the index)."""
        agent_type, config_dir = await self._catalog.resolve(agent_name)
        sessions = await asyncio.to_thread(
            self._reader.list_sessions, agent_type_value=agent_type, config_dir=config_dir
        )
        return [self._session_ref(s) for s in sessions]

    async def browse(self, *, agent_name: str, session_id: str) -> HistorySessionDetail:
        """Read one session's scrubbed turns on demand. Never writes."""
        agent_type, config_dir = await self._catalog.resolve(agent_name)
        session = await asyncio.to_thread(
            self._reader.read_session,
            agent_type_value=agent_type,
            config_dir=config_dir,
            session_id=session_id,
        )
        turns = tuple(HistoryTurn(role=m.role, text=m.text) for m in session.messages)
        return HistorySessionDetail(ref=self._session_ref(session), turns=turns)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _store() -> StoreRef:
        # ``docs_dir`` is unused (history never greps); the index keys off
        # (kind, resource_name) only.
        return StoreRef(
            kind=KIND_TRANSCRIPT,
            resource_name=RESOURCE_NAME,
            project_id=WORKSPACE_GLOBAL_PROJECT_ID,
            docs_dir="",
        )

    @staticmethod
    def _doc_id(agent_type: str, session_id: str) -> str:
        return f"{agent_type}:{session_id}"

    async def _list_docs(self) -> list[Document]:
        return await self._documents.list_documents(
            KIND_TRANSCRIPT, RESOURCE_NAME, limit=1_000_000, offset=0
        )

    def _session_to_document(self, session: TranscriptSession, *, content_sha256: str) -> Document:
        now = datetime.now(tz=UTC)
        started = session.started_at
        return Document(
            id=self._doc_id(session.agent_type_value, session.session_id),
            kind=KIND_TRANSCRIPT,
            resource_name=RESOURCE_NAME,
            project_id=WORKSPACE_GLOBAL_PROJECT_ID,
            path=session.source_path,
            title=self._title(session),
            description=None,
            content_sha256=content_sha256,
            source_mode="native",
            created_at=started or now,
            updated_at=now,
            metadata={
                "agent_type": session.agent_type_value,
                "session_id": session.session_id,
                "project_path": session.project_path,
                "started_at": started.isoformat() if started else None,
                "message_count": session.message_count,
            },
        )

    def _session_ref(self, session: TranscriptSession) -> HistorySessionRef:
        return HistorySessionRef(
            agent_type=session.agent_type_value,
            session_id=session.session_id,
            project_path=session.project_path,
            started_at=session.started_at,
            title=self._title(session),
            message_count=session.message_count,
        )

    @staticmethod
    def _title(session: TranscriptSession) -> str:
        project = (
            session.project_path.rstrip("/").rsplit("/", 1)[-1] if session.project_path else "—"
        )
        return f"{session.agent_type_value} · {project}"


def _parse_iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
