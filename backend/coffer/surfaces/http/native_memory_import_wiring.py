"""Composition root for native-memory ADOPTION (spec 004, FR-041).

Wires ``AgentMemoryImportService`` — the slice that imports a coding agent's OWN
native per-project memory into Coffer memory. Like ``distill_wiring``, this is the
boundary site where ``agent`` + ``memory`` + ``organizer`` meet: ``application.agent``
may not import the memory kind (Contract 5b), so the memory write/organize/store-name
plumbing is reached only through a composition-root sink adapter.

Must be called AFTER ``wire_organize`` (so ``get_organizer_service`` is populated)
and with a live ``MemoryService`` + ``AgentService``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from coffer.application.agent.memory_import_service import AgentMemoryImportService
from coffer.application.memory.service import MemoryService
from coffer.application.memory.stores import store_name_for
from coffer.domain.agent.native_memory import ParsedNativeFact
from coffer.domain.memory.config import MAX_FACT_CHARS
from coffer.domain.memory.scope import MemoryScope
from coffer.infrastructure.agent.native_memory_import import (
    read_memory_facts,
    resolve_project_path,
)
from coffer.surfaces.http.dependencies import set_agent_memory_import_service

logger = logging.getLogger(__name__)

# Holds live background organize tasks so they are not garbage-collected mid-run
# (asyncio keeps only a weak reference to a bare create_task result).
_IMPORT_ORGANIZE_TASKS: set[asyncio.Task[None]] = set()


class _Reader:
    """NativeMemoryReaderPort adapter: delegates to the pure infra helpers."""

    def read_facts(self, memory_dir: str) -> list[ParsedNativeFact]:
        from pathlib import Path

        return read_memory_facts(Path(memory_dir))

    def resolve_project_path(self, memory_dir: str) -> str | None:
        from pathlib import Path

        return resolve_project_path(Path(memory_dir))


class _ImportSink:
    """MemoryImportSinkPort adapter: writes each fact via MemoryService.add_fact,
    organizes via the registered OrganizerService, and resolves the store name."""

    def __init__(self, memory_service: MemoryService) -> None:
        self._memory = memory_service

    async def add(
        self,
        *,
        project_path: str,
        title: str,
        description: str,
        body: str,
        origin_session_id: str | None,
    ) -> None:
        # Raises ScopeUnresolved if project_path is not inside a git work-tree;
        # the import service catches it and aborts cleanly. A trusted bulk import
        # of the user's OWN existing memory writes up to the domain ceiling so a
        # long note is never rejected (the store's smaller default bounds ordinary
        # agent ``remember`` writes, not this import).
        await self._memory.add_fact(
            scope=MemoryScope.PROJECT,
            cwd=project_path,
            title=title,
            description=description,
            body=body,
            actor="agent",
            origin_session_id=origin_session_id,
            max_fact_chars=MAX_FACT_CHARS,
        )

    async def store_name(self, *, project_path: str) -> str | None:
        try:
            resolved = await self._memory.resolve_scope(scope=MemoryScope.PROJECT, cwd=project_path)
        except Exception:
            return None
        return store_name_for(resolved)

    async def organize(self, *, project_path: str) -> bool:
        """SCHEDULE the organizer for the project store as a background task and
        return immediately. A bulk import seeds dozens of inbox items; organizing
        them is dozens of sequential internal-LLM calls (minutes), so it must NOT
        block the import request — that would hang or time out the caller (and the
        organize would die if the client disconnects). Returns whether organize was
        scheduled (False only when the store can't be resolved)."""
        store = await self.store_name(project_path=project_path)
        if store is None:
            return False
        task = asyncio.create_task(self._organize_in_background(store))
        _IMPORT_ORGANIZE_TASKS.add(task)
        task.add_done_callback(_IMPORT_ORGANIZE_TASKS.discard)
        return True

    async def _organize_in_background(self, store_name: str) -> None:
        # Lazy import: the organizer is registered by wire_organize at startup,
        # which runs after this module is imported (avoids an import-time cycle).
        from coffer.surfaces.http.memory.organize_state import get_organizer_service

        try:
            await get_organizer_service().organize(store_name=store_name)
        except Exception:
            logger.warning("native_memory_import.organize_failed", exc_info=True)


def wire_native_memory_import(memory_service: MemoryService, agent_service: Any) -> None:
    """Construct + register ``AgentMemoryImportService``.

    Call AFTER ``wire_organize`` so the organizer is reachable via
    ``get_organizer_service`` from ``_ImportSink.organize``.
    """
    svc = AgentMemoryImportService(
        agent_service=agent_service,
        reader=_Reader(),
        sink=_ImportSink(memory_service),
    )
    set_agent_memory_import_service(svc)
