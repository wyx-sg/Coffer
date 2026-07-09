# backend/coffer/application/memory/journal.py
"""Journal lane (episodic): append-only events per project store.

Mirrors ``HandoffService`` but is project-scoped (no branch keying) and
append-only (no overwrite). The journal is fed internally (transcript
distillation), **indexed for recall** (FR-043 — the reconciler projects each
``journal/<period>.md`` into a ``documents`` row), and synced as source-of-truth
history. On append the period file is indexed immediately (reconcile-on-append)
so a distilled entry is searchable without waiting for a lazy reconcile-on-read.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path

from coffer.application.audit_service import AuditService
from coffer.application.memory.scope import ScopeResolver, project_store_name
from coffer.application.memory.stores import build_store_ref_for
from coffer.application.memory.sync import MemoryReconciler
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ScopeUnresolved
from coffer.domain.knowledge.document import KIND_MEMORY
from coffer.domain.knowledge.embedder import EmbeddingConfig
from coffer.domain.memory.journal import JournalEntry
from coffer.domain.memory.scope import MemoryScope
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.knowledge.paths import journal_dir, journal_path
from coffer.infrastructure.memory import journal_files as jf

StoreDirFn = Callable[[str], Path]
ClockFn = Callable[[], datetime]
EmbeddingResolverFn = Callable[[], Awaitable["EmbeddingConfig | None"]]

_log = logging.getLogger("coffer.memory.journal")


class JournalService:
    """Append/read the episodic journal for the current project store."""

    def __init__(
        self,
        *,
        scope: ScopeResolver,
        store_dir: StoreDirFn,
        audit: AuditService,
        now: ClockFn,
        reconciler: MemoryReconciler | None = None,
        embedding: EmbeddingResolverFn | None = None,
    ) -> None:
        self._scope = scope
        self._store_dir = store_dir
        self._audit = audit
        self._now = now
        # Optional reconcile-on-append: when wired, an appended period file is
        # indexed immediately so it is recall-able without a lazy reconcile.
        self._reconciler = reconciler
        self._embedding = embedding

    async def _store(self, cwd: str | None) -> tuple[Path, str, str] | None:
        """Resolve ``(store_dir, store_name, project_id)`` for ``cwd``, or
        ``None`` when the cwd is not inside a git project (no global journal)."""
        if cwd is None:
            return None
        try:
            resolved = await self._scope.resolve(scope=MemoryScope.PROJECT, cwd=cwd)
        except ScopeUnresolved:
            return None
        return (
            self._store_dir(resolved.project_id),
            project_store_name(resolved.project_id),
            resolved.project_id,
        )

    async def append(self, *, cwd: str | None, body: str, actor: str) -> JournalEntry | None:
        """Append one episodic event to the current project's journal.

        A blank/whitespace-only body is skipped: nothing is written, no audit
        event is recorded, and ``None`` is returned (so an empty distillation
        leaves no journal entry and no ``journal/<YYYY-MM-DD>.md`` file)."""
        if not body.strip():
            return None
        located = await self._store(cwd)
        if located is None:
            raise ScopeUnresolved(cwd or "<none>")
        store_dir, store_name, project_id = located
        ts = self._now()
        period = jf.journal_period(ts)
        jf.append_entry(journal_path(store_dir, period), timestamp=ts, body=body)
        await self._audit.record(
            AuditEventType.JOURNAL_APPEND.value,
            ref=ResourceRef(KIND_MEMORY, store_name),
            actor=actor,
            details={"char_size": len(body)},
        )
        await self._index_period(store_name, project_id, period)
        return JournalEntry(timestamp=ts, body=body.strip())

    async def _index_period(self, store_name: str, project_id: str, period: str) -> None:
        """Index the just-appended period file so the entry is recall-able now
        (FR-043). Best-effort: a failure leaves the file on disk for the next
        reconcile-on-read to pick up, so it never blocks the append."""
        if self._reconciler is None:
            return
        try:
            embedding = await self._embedding() if self._embedding is not None else None
            ref = build_store_ref_for(store_name, project_id, store_dir=self._store_dir)
            await self._reconciler.index_journal_period(
                store=ref, period=period, embedding=embedding
            )
        except Exception:
            _log.exception("journal.index_on_append.failed store=%s", store_name)

    async def read_recent(self, *, cwd: str | None, limit: int = 20) -> list[JournalEntry]:
        """Return the most recent journal entries (newest-first), or ``[]``."""
        located = await self._store(cwd)
        if located is None:
            return []
        store_dir, _, _ = located
        d = journal_dir(store_dir)
        entries: list[JournalEntry] = []
        if d.exists():
            for f in sorted(d.glob("*.md"), reverse=True):
                entries.extend(jf.read_entries(f))
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        # ``limit`` is a hard cap: ``limit=0`` returns ``[]`` (no implicit "all").
        return entries[:limit]
