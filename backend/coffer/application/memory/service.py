"""MemoryService — orchestration for the memory kind.

Knows nothing about mem0; talks only to the MemoryStore port and the
MemoryRecordRepo port.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import (
    LLMNotConfigured,
    MemoryNotFound,
    MemoryRejected,
    MemoryStoreNotFound,
)
from coffer.domain.memory.config import MemoryStoreConfig
from coffer.domain.memory.record import Actor, MemoryRecord
from coffer.domain.memory.store import MemoryHit, MemoryStore
from coffer.domain.resource import ResourceRef


class MemoryRecordRepo(Protocol):
    async def create(self, m: MemoryRecord) -> MemoryRecord: ...
    async def get(self, store_name: str, memory_id: str) -> MemoryRecord | None: ...
    async def list_by_store(
        self, store_name: str, *, limit: int, offset: int
    ) -> list[MemoryRecord]: ...
    async def count_by_store(self, store_name: str) -> int: ...
    async def update_text(
        self, store_name: str, memory_id: str, new_text: str, updated_at: datetime
    ) -> MemoryRecord: ...
    async def delete(self, store_name: str, memory_id: str) -> bool: ...
    async def delete_all_by_store(self, store_name: str) -> int: ...


class MemoryService:
    def __init__(
        self,
        *,
        resource_service: ResourceService,
        store: MemoryStore,
        records: MemoryRecordRepo,
        audit: AuditService,
        store_dir: Callable[[str], Path],
    ) -> None:
        self._resources = resource_service
        self._store = store
        self._records = records
        self._audit = audit
        self._store_dir = store_dir

    # ----- store-level -----

    async def get_store_config(self, store_name: str) -> MemoryStoreConfig:
        ref = ResourceRef(kind="memory", name=store_name)
        try:
            resource = await self._resources.get(ref)
        except Exception as exc:
            raise MemoryStoreNotFound(store_name) from exc
        return MemoryStoreConfig.model_validate(resource.config)

    # ----- memory-level -----

    async def add(self, *, store_name: str, text: str, actor: Actor) -> MemoryRecord:
        config = await self.get_store_config(store_name)
        _validate_text(text, config.max_memory_chars)
        if config.llm_provider == "none":
            raise LLMNotConfigured(store_name)
        await self._store.open(store_name, config)
        try:
            record = await self._store.add(store_name, text, actor)
        except MemoryRejected as exc:
            # CODE26-015: mem0 may decide the text duplicates an existing
            # memory and "not store" it. Without an audit trail the merge
            # is invisible. Emit a dedicated ``memory_merged`` event so
            # operators can correlate the rejection with the dedup
            # decision, then re-raise so the surface still returns the
            # 400 envelope (mem0 does not give us the existing id to
            # return). Other reasons (empty / too_long / etc.) just
            # propagate unchanged.
            if exc.reason == "not_stored":
                await self._audit.record(
                    AuditEventType.MEMORY_MERGED.value,
                    ref=ResourceRef("memory", store_name),
                    actor=actor,
                    details={"char_size": len(text), "reason": exc.reason},
                )
            raise
        persisted = await self._records.create(record)
        await self._audit.record(
            AuditEventType.MEMORY_ADDED.value,
            ref=ResourceRef("memory", store_name),
            actor=actor,
            details={"memory_id": persisted.id, "char_size": len(text)},
        )
        return persisted

    async def list_memories(
        self, *, store_name: str, limit: int, offset: int
    ) -> tuple[list[MemoryRecord], int]:
        await self.get_store_config(store_name)
        rows = await self._records.list_by_store(store_name, limit=limit, offset=offset)
        total = await self._records.count_by_store(store_name)
        return rows, total

    async def get(self, *, store_name: str, memory_id: str) -> MemoryRecord:
        row = await self._records.get(store_name, memory_id)
        if row is None:
            raise MemoryNotFound(store_name, memory_id)
        return row

    async def update(
        self, *, store_name: str, memory_id: str, new_text: str, actor: Actor
    ) -> MemoryRecord:
        config = await self.get_store_config(store_name)
        _validate_text(new_text, config.max_memory_chars)
        # CODE26-009: spec FR-014 allows edits even when no LLM is wired —
        # mem0's update path overwrites the canonical text directly and does
        # not require a fresh round of fact-extraction. Don't gate on
        # ``llm_provider == "none"`` here.
        before = await self._records.get(store_name, memory_id)
        if before is None:
            raise MemoryNotFound(store_name, memory_id)
        await self._store.open(store_name, config)
        # CODE26-023: pass actor down so the adapter can stamp it on the
        # returned record (mem0 itself does not track update-time actor).
        updated = await self._store.update(store_name, memory_id, new_text, actor=actor)
        now = datetime.now(tz=UTC)
        persisted = await self._records.update_text(
            store_name, memory_id, new_text=updated.text, updated_at=now
        )
        await self._audit.record(
            AuditEventType.MEMORY_UPDATED.value,
            ref=ResourceRef("memory", store_name),
            actor=actor,
            details={
                "memory_id": memory_id,
                "before_char_size": len(before.text),
                "after_char_size": len(persisted.text),
            },
        )
        return persisted

    async def delete(self, *, store_name: str, memory_id: str, actor: str) -> None:
        config = await self.get_store_config(store_name)
        record = await self._records.get(store_name, memory_id)
        if record is None:
            raise MemoryNotFound(store_name, memory_id)
        await self._store.open(store_name, config)
        await self._store.delete(store_name, memory_id)
        await self._records.delete(store_name, memory_id)
        await self._audit.record(
            AuditEventType.MEMORY_DELETED.value,
            ref=ResourceRef("memory", store_name),
            actor=actor,
            details={"memory_id": memory_id},
        )

    async def clear(self, *, store_name: str, actor: str) -> int:
        config = await self.get_store_config(store_name)
        await self._store.open(store_name, config)
        cleared_from_store = await self._store.clear(store_name)
        cleared_from_rows = await self._records.delete_all_by_store(store_name)
        cleared = max(cleared_from_store, cleared_from_rows)
        await self._audit.record(
            AuditEventType.MEMORY_CLEARED.value,
            ref=ResourceRef("memory", store_name),
            actor=actor,
            details={"cleared": cleared},
        )
        return cleared

    async def search(self, *, store_name: str, query: str, top_k: int) -> list[MemoryHit]:
        config = await self.get_store_config(store_name)
        await self._store.open(store_name, config)
        hits = list(await self._store.search(store_name, query, top_k))
        return hits

    async def metrics(self, *, store_name: str) -> tuple[int, int]:
        await self.get_store_config(store_name)
        count = await self._records.count_by_store(store_name)
        d = self._store_dir(store_name)
        disk = _du(d) if d.exists() else 0
        return count, disk

    # Used by the on_delete kind hook.
    async def cleanup_store(self, store_name: str) -> None:
        """Tear down a memory store's three forms of state.

        CODE26-020: each phase runs even if a previous phase fails — a
        broken mem0 client would otherwise orphan SQL rows and an on-disk
        chroma directory after the Resource row is gone. Each failure is
        suppressed individually so the caller's ``on_delete`` hook never
        observes a half-completed teardown.
        """
        import contextlib
        import logging
        import shutil

        _logger = logging.getLogger(__name__)

        try:
            await self._store.drop(store_name)
        except Exception:
            _logger.warning(
                "memory.cleanup.drop_failed",
                extra={"store_name": store_name},
                exc_info=True,
            )
        with contextlib.suppress(Exception):
            await self._records.delete_all_by_store(store_name)
        d = self._store_dir(store_name)
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)


def _validate_text(text: str, max_chars: int) -> None:
    if not text or not text.strip():
        raise MemoryRejected("empty", "memory text is empty")
    if len(text) > max_chars:
        raise MemoryRejected(
            "too_long",
            f"memory text length {len(text)} exceeds store limit {max_chars}",
        )


def _du(path: Path) -> int:
    import contextlib

    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            with contextlib.suppress(OSError):
                total += p.stat().st_size
    return total


# Used by the kind on_delete; surface untyped to avoid Callable typing churn.
_DeleteHook = Callable[[ResourceRef], Awaitable[None]]
