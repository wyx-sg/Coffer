# backend/coffer/application/memory/journal.py
"""Journal lane (episodic): append-only events per project store.

Mirrors ``HandoffService`` but is project-scoped (no branch keying) and
append-only (no overwrite). The journal is fed internally (distillation in a
later slice), excluded from recall, and synced as source-of-truth history.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from coffer.application.audit_service import AuditService
from coffer.application.memory.scope import ScopeResolver, project_store_name
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ScopeUnresolved
from coffer.domain.knowledge.document import KIND_MEMORY
from coffer.domain.memory.journal import JournalEntry
from coffer.domain.memory.scope import MemoryScope
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.knowledge.paths import journal_dir, journal_path
from coffer.infrastructure.memory import journal_files as jf

StoreDirFn = Callable[[str], Path]
ClockFn = Callable[[], datetime]


class JournalService:
    """Append/read the episodic journal for the current project store."""

    def __init__(
        self,
        *,
        scope: ScopeResolver,
        store_dir: StoreDirFn,
        audit: AuditService,
        now: ClockFn,
    ) -> None:
        self._scope = scope
        self._store_dir = store_dir
        self._audit = audit
        self._now = now

    async def _store(self, cwd: str | None) -> tuple[Path, str] | None:
        """Resolve ``(store_dir, store_name)`` for ``cwd``, or ``None`` when the
        cwd is not inside a git project (no global journal)."""
        if cwd is None:
            return None
        try:
            resolved = await self._scope.resolve(scope=MemoryScope.PROJECT, cwd=cwd)
        except ScopeUnresolved:
            return None
        return self._store_dir(resolved.project_id), project_store_name(resolved.project_id)

    async def append(self, *, cwd: str | None, body: str, actor: str) -> JournalEntry:
        """Append one episodic event to the current project's journal."""
        located = await self._store(cwd)
        if located is None:
            raise ScopeUnresolved(cwd or "<none>")
        store_dir, store_name = located
        ts = self._now()
        jf.append_entry(journal_path(store_dir, jf.journal_period(ts)), timestamp=ts, body=body)
        await self._audit.record(
            AuditEventType.JOURNAL_APPEND.value,
            ref=ResourceRef(KIND_MEMORY, store_name),
            actor=actor,
            details={"char_size": len(body)},
        )
        return JournalEntry(timestamp=ts, body=body.strip())

    async def read_recent(self, *, cwd: str | None, limit: int = 20) -> list[JournalEntry]:
        """Return the most recent journal entries (newest-first), or ``[]``."""
        located = await self._store(cwd)
        if located is None:
            return []
        store_dir, _ = located
        d = journal_dir(store_dir)
        entries: list[JournalEntry] = []
        if d.exists():
            for f in sorted(d.glob("*.md"), reverse=True):
                entries.extend(jf.read_entries(f))
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        # ``limit`` is a hard cap: ``limit=0`` returns ``[]`` (no implicit "all").
        return entries[:limit]
