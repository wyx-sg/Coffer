"""Composition root for native-memory ADOPTION (spec 004, FR-041).

Wires ``AgentMemoryImportService`` — the slice that imports a coding agent's OWN
native per-project memory into Coffer memory. This is the boundary site where
``agent`` + ``memory`` + ``organizer`` meet: ``application.agent``
may not import the knowledge kind (Contract 5b), so the write/organize/scope-name
plumbing is reached only through a composition-root sink adapter.

Must be called AFTER ``wire_organize`` (so ``get_organizer_service`` is populated)
and with a live ``KnowledgeService`` + ``AgentService``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from coffer.application.agent.memory_import_service import AgentMemoryImportService
from coffer.application.knowledge.service import KnowledgeService
from coffer.application.knowledge.stores import scope_name_for
from coffer.domain.agent.native_memory import ParsedNativeFact
from coffer.domain.knowledge.scope import KnowledgeScope
from coffer.domain.knowledge.scope_config import MAX_ENTRY_CHARS
from coffer.infrastructure.agent.codex_memory_store import read_codex_facts
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

    def read_codex_facts(self, memory_dir: str, project_path: str) -> list[ParsedNativeFact]:
        from pathlib import Path

        return read_codex_facts(Path(memory_dir), project_path, "MEMORY.md")


class _ImportSink:
    """MemoryImportSinkPort adapter: writes each fact via KnowledgeService.add_fact,
    organizes via the registered OrganizerService, and resolves the scope name
    under the port's ``store_name`` (the agent-side port is not ours to rename)."""

    def __init__(self, memory_service: KnowledgeService) -> None:
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
        # long note is never rejected (the scope's smaller default bounds ordinary
        # agent writes, not this import).
        await self._memory.add_fact(
            scope=KnowledgeScope.PROJECT,
            cwd=project_path,
            title=title,
            description=description,
            body=body,
            actor="agent",
            origin_session_id=origin_session_id,
            max_entry_chars=MAX_ENTRY_CHARS,
        )

    async def store_name(self, *, project_path: str) -> str | None:
        try:
            resolved = await self._memory.resolve_scope(
                scope=KnowledgeScope.PROJECT, cwd=project_path
            )
        except Exception:
            return None
        return scope_name_for(resolved)

    async def organize(self, *, project_path: str) -> bool:
        """SCHEDULE the organizer for the project scope as a background task and
        return immediately. A bulk import seeds dozens of inbox items; organizing
        them is dozens of sequential internal-LLM calls (minutes), so it must NOT
        block the import request — that would hang or time out the caller (and the
        organize would die if the client disconnects). Returns whether organize was
        scheduled (False only when the scope can't be resolved)."""
        scope = await self.store_name(project_path=project_path)
        if scope is None:
            return False
        task = asyncio.create_task(self._organize_in_background(scope))
        _IMPORT_ORGANIZE_TASKS.add(task)
        task.add_done_callback(_IMPORT_ORGANIZE_TASKS.discard)
        return True

    async def _organize_in_background(self, scope_name: str) -> None:
        # Lazy import: the organizer is registered by wire_organize at startup,
        # which runs after this module is imported (avoids an import-time cycle).
        from coffer.surfaces.http.knowledge.organize_state import get_organizer_service

        try:
            await get_organizer_service().organize(scope_name=scope_name)
        except Exception:
            logger.warning("native_memory_import.organize_failed", exc_info=True)


def wire_native_memory_import(memory_service: KnowledgeService, agent_service: Any) -> None:
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
