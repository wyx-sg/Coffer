"""AgentMemoryImportService — ADOPT a coding agent's OWN native per-project memory.

Treats the agent's on-disk native memory (Claude Code's
``<config_dir>/projects/<slug>/memory/*.md``) as a batch of ``remember`` writes:
resolve the store's REAL project path, parse every fact file, write each into
Coffer's project-scoped memory inbox, then run the internal organizer once.

Cross-kind boundary (Contract 5b): ``application.agent`` may NOT import the
memory kind, so the memory write/organize/store-name plumbing is reached only
through ``MemoryImportSinkPort`` — wired by a composition-root adapter, exactly
like transcript distillation's insight sink. The reader port hides the infra
parse/resolution helpers. This module imports neither memory nor infrastructure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from coffer.domain.agent.native_memory import ParsedNativeFact
from coffer.domain.errors import MemoryRejected, ScopeUnresolved
from coffer.domain.resource import Resource

logger = logging.getLogger(__name__)


class NativeMemoryReaderPort(Protocol):
    """Parse + resolve a native memory dir. Implemented over infra in the root."""

    def read_facts(self, memory_dir: str) -> list[ParsedNativeFact]:
        """Every fact file in ``memory_dir`` (the ``MEMORY.md`` index excluded)."""
        ...

    def resolve_project_path(self, memory_dir: str) -> str | None:
        """The REAL absolute project path for ``memory_dir``, or ``None``."""
        ...


class MemoryImportSinkPort(Protocol):
    """Write/organize boundary into the memory kind (composition-root adapter)."""

    async def add(
        self,
        *,
        project_path: str,
        title: str,
        description: str,
        body: str,
        origin_session_id: str | None,
    ) -> None:
        """Write one fact to the project-scoped memory inbox.

        Raises ``ScopeUnresolved`` if ``project_path`` is not inside a git
        project (it then maps to no Coffer project store)."""
        ...

    async def organize(self, *, project_path: str) -> bool:
        """Run the internal organizer for the project store; return whether it
        ran without error (a ``no_model``/``empty`` no-op counts as ``True``)."""
        ...

    async def store_name(self, *, project_path: str) -> str | None:
        """The resolved memory store name for ``project_path`` (or ``None``)."""
        ...


# Structural type for the agent-lookup dependency — avoids a hard import of
# AgentService and keeps this service unit-testable with a fake (mirrors
# native_memory_service._AgentLookup).
class _AgentLookup(Protocol):
    async def get(self, name: str) -> Resource: ...


@dataclass(frozen=True)
class ImportResult:
    """The outcome of one native-memory adoption run."""

    imported: int
    skipped: int
    store: str | None
    project_path: str | None
    organized: bool


class AgentMemoryImportService:
    """Adopt an agent's native per-project memory into Coffer memory."""

    def __init__(
        self,
        *,
        agent_service: _AgentLookup,
        reader: NativeMemoryReaderPort,
        sink: MemoryImportSinkPort,
    ) -> None:
        self._agents = agent_service
        self._reader = reader
        self._sink = sink

    async def import_store(self, *, name: str, memory_dir: str) -> ImportResult:
        """Import ``memory_dir`` into the agent's project memory, then organize.

        Raises ``ResourceNotFound`` (→ 404) for an unknown agent. A path that
        can't be resolved, an empty/absent dir, or a non-git project all return
        a zero-import result rather than erroring — the inbox is never corrupted.
        """
        # Raises ResourceNotFound (→ 404) when the agent doesn't exist.
        await self._agents.get(name)

        project_path = self._reader.resolve_project_path(memory_dir)
        facts = self._reader.read_facts(memory_dir)
        if project_path is None or not facts:
            return ImportResult(
                imported=0,
                skipped=len(facts),
                store=None,
                project_path=project_path,
                organized=False,
            )

        imported = 0
        skipped = 0
        for fact in facts:
            try:
                await self._sink.add(
                    project_path=project_path,
                    # ``ParsedNativeFact.name`` is the upstream agent format's own
                    # field; it maps onto the Coffer fact ``title`` at the sink.
                    title=fact.name,
                    description=fact.description,
                    body=fact.body,
                    origin_session_id=fact.origin_session_id,
                )
            except ScopeUnresolved:
                # The resolved path is not a git project → it maps to no Coffer
                # project store. Abort cleanly; nothing was committed.
                return ImportResult(
                    imported=0,
                    skipped=len(facts),
                    store=None,
                    project_path=project_path,
                    organized=False,
                )
            except MemoryRejected:
                # One fact was rejected (e.g. its body exceeds the store's length
                # limit) — skip it and keep importing the rest. A single bad fact
                # must never abort the whole batch.
                skipped += 1
                continue
            imported += 1

        store = await self._sink.store_name(project_path=project_path)
        organized = await self._organize(project_path=project_path) if imported else False
        return ImportResult(
            imported=imported,
            skipped=skipped,
            store=store,
            project_path=project_path,
            organized=organized,
        )

    async def _organize(self, *, project_path: str) -> bool:
        """Organize, swallowing any failure so a successful import is never lost."""
        try:
            return await self._sink.organize(project_path=project_path)
        except Exception:
            logger.warning(
                "memory_import.organize_failed: imported items kept in inbox",
                exc_info=True,
            )
            return False


__all__ = [
    "AgentMemoryImportService",
    "ImportResult",
    "MemoryImportSinkPort",
    "NativeMemoryReaderPort",
]
