"""The memory sync: publish this machine's agents' memories to the hub, then
write the hub into this machine's agents (spec memory "Sync on an interval
and on demand").

One sync at a time. A sync:

1. **publishes** (``sync_publish``): reads each registered agent's native
   memory and commits the hub's changes as one vault commit;
2. **plans** the copies for each local agent (``sync_write``);
3. **writes** them — or, on the first sync on this machine and whenever more
   than :data:`PREVIEW_THRESHOLD` copies would be written, saves the plan as a
   preview the person confirms on the Memory page ("Preview a first or large
   sync"). Publishing never waits for the preview;
4. records one ``memory_synced`` event when it changed anything ("Record
   every sync in Activity").

The work is file I/O and git, so each operation runs in a worker thread under
one asyncio lock.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from coffer.application.memory.sources import AgentSource
from coffer.application.memory.sync_publish import FindSecret, PublishContext, publish
from coffer.application.memory.sync_report import SyncReport, preview_summary
from coffer.application.memory.sync_write import (
    AgentTargets,
    LocalAgent,
    apply_ops,
    plan_agent,
    targets_for,
    undo_agent,
)
from coffer.application.upkeep_runs import UPKEEP_RUNS
from coffer.domain.audit import AuditEventType
from coffer.domain.memory.errors import MemorySyncNoPreview, MemorySyncRunning
from coffer.domain.memory.hub import HubEntry
from coffer.domain.memory.native_writer import NativeWriter
from coffer.domain.memory.reader import MemoryReader
from coffer.domain.memory.sync_plan import PREVIEW_THRESHOLD, AgentPlan, CopyOp
from coffer.infrastructure.memory import checkouts as checkout_map
from coffer.infrastructure.memory.hub_store import HubStore
from coffer.infrastructure.memory.sync_ledger import Ledger, LedgerStore, PreviewStore

logger = logging.getLogger(__name__)


#: The memory sync's key in the daemon's table of passes in flight, which
#: ``coffer daemon status`` reads (spec resource-framework "Report the passes in
#: flight in one cross-kind read").
SYNC_RUN = ("memory", "sync")


class AuditPort(Protocol):
    async def record(
        self, event_type: str, *, actor: str = ..., details: dict[str, Any] | None = ...
    ) -> None: ...


AgentLister = Callable[[], Awaitable[Sequence[AgentSource]]]


def _now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class _Planned:
    local: LocalAgent
    writer: NativeWriter
    targets: AgentTargets
    plan: AgentPlan


class MemorySyncService:
    def __init__(
        self,
        *,
        agents: AgentLister,
        readers: Mapping[str, MemoryReader],
        writers: Mapping[str, NativeWriter],
        audit: AuditPort,
        machine: Callable[[], str],
        home: Callable[[], str],
        find_secret: FindSecret,
        hub: HubStore | None = None,
        ledger: LedgerStore | None = None,
        previews: PreviewStore | None = None,
        now: Callable[[], str] = _now,
        threshold: int = PREVIEW_THRESHOLD,
        stop_automatic: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self._agents = agents
        self._readers = readers
        self._writers = writers
        self._audit = audit
        self._machine = machine
        self._home = home
        self._find_secret = find_secret
        self.hub = hub or HubStore()
        self.ledger = ledger or LedgerStore()
        self.previews = previews or PreviewStore()
        self._now = now
        self._threshold = threshold
        self._lock = asyncio.Lock()
        self._stop_automatic = stop_automatic

    @property
    def running(self) -> bool:
        return self._lock.locked()

    @property
    def writers(self) -> Mapping[str, NativeWriter]:
        return self._writers

    async def local_agents(self) -> list[LocalAgent]:
        return [
            LocalAgent(agent=a.agent, agent_type=a.agent_type, config_dir=a.config_dir)
            for a in await self._agents()
            if a.agent_type in self._writers or a.agent_type in self._readers
        ]

    # --- operations ----------------------------------------------------------

    async def sync(self, actor: str) -> SyncReport:
        """Run one sync; ``MemorySyncRunning`` while another runs."""
        if self._lock.locked():
            raise MemorySyncRunning()
        async with self._lock:
            agents = list(await self._agents())
            with UPKEEP_RUNS.guard(*SYNC_RUN):
                report = await asyncio.to_thread(self._sync, agents, actor)
        await self._record(AuditEventType.MEMORY_SYNCED, actor, report)
        return report

    async def write_preview(self, actor: str) -> SyncReport:
        """Write exactly what the pending preview listed."""
        if self._lock.locked():
            raise MemorySyncRunning()
        async with self._lock:
            agents = list(await self._agents())
            with UPKEEP_RUNS.guard(*SYNC_RUN):
                report = await asyncio.to_thread(self._write_preview, agents)
        await self._record(AuditEventType.MEMORY_SYNCED, actor, report)
        return report

    async def cancel_preview(self) -> None:
        if self.previews.load() is None:
            raise MemorySyncNoPreview()
        self.previews.clear()

    async def undo(self, actor: str) -> SyncReport:
        """Remove every unedited copy, Coffer's block, rules file and
        extension folder from this machine's agents ("Undo sync")."""
        if self._lock.locked():
            raise MemorySyncRunning()
        async with self._lock:
            agents = list(await self._agents())
            with UPKEEP_RUNS.guard(*SYNC_RUN):
                report = await asyncio.to_thread(self._undo, agents)
        if self._stop_automatic is not None:
            await self._stop_automatic(actor)
        await self._audit.record(
            AuditEventType.MEMORY_SYNC_UNDONE.value, actor=actor, details=report.details()
        )
        return report

    async def set_codex_imports_claude(self, value: bool | None) -> None:
        async with self._lock:
            ledger = self.ledger.load()
            ledger.codex_imports_claude = value
            self.ledger.save(ledger)

    # --- the work, in a thread -----------------------------------------------

    def _sync(self, agents: Sequence[AgentSource], actor: str) -> SyncReport:
        ledger = self.ledger.load()
        machine, home, now = self._machine(), self._home(), self._now()
        hub = self.hub.entries()
        ctx = PublishContext(
            machine=machine,
            home=home,
            now=now,
            find_secret=self._find_secret,
            project_of=checkout_map.project_of,
        )
        published = publish(agents, self._readers, hub, ledger, ctx)
        report = SyncReport.from_publish(published)
        if published.changes:
            self.hub.apply(published.changes, _summary(published.changes), actor)
            hub = self.hub.entries()

        planned = self._plan(agents, hub, ledger, report)
        ops = [op for p in planned for op in p.plan.ops]
        pending_globals = any(p.targets.globals for p in planned) and not ledger.previewed
        if (ops or pending_globals) and (not ledger.previewed or len(ops) > self._threshold):
            self.previews.save(now, ops)
            report.preview = preview_summary(ops, planned_globals(planned))
        else:
            self.previews.clear()
            for p in planned:
                done = apply_ops(p.writer, p.local, p.plan.ops, p.targets, p.plan.records, ledger)
                report.add_applied(p.local, done)
        ledger.last_synced_at = now
        ledger.last_report = report.summary()
        self.ledger.save(ledger)
        return report

    def _write_preview(self, agents: Sequence[AgentSource]) -> SyncReport:
        pending = self.previews.load()
        if pending is None:
            raise MemorySyncNoPreview()
        _, listed = pending
        wanted = {_op_key(op) for op in listed}
        ledger = self.ledger.load()
        report = SyncReport()
        planned = self._plan(agents, self.hub.entries(), ledger, report)
        for p in planned:
            ops = [op for op in p.plan.ops if _op_key(op) in wanted]
            done = apply_ops(p.writer, p.local, ops, p.targets, p.plan.records, ledger)
            report.add_applied(p.local, done)
        ledger.previewed = True
        ledger.last_synced_at = self._now()
        ledger.last_report = report.summary()
        self.ledger.save(ledger)
        self.previews.clear()
        return report

    def _undo(self, agents: Sequence[AgentSource]) -> SyncReport:
        ledger = self.ledger.load()
        report = SyncReport()
        for local in _locals(agents):
            writer = self._writers.get(local.agent_type)
            if writer is None:
                continue
            report.add_applied(local, undo_agent(writer, local, ledger))
        ledger.previewed = False
        self.ledger.save(ledger)
        self.previews.clear()
        return report

    def _plan(
        self,
        agents: Sequence[AgentSource],
        hub: Mapping[str, HubEntry],
        ledger: Ledger,
        report: SyncReport,
    ) -> list[_Planned]:
        locals_ = _locals(agents)
        dirs = [
            d
            for local in locals_
            for d in checkout_map.recorded_dirs(local.agent_type, local.config_dir)
        ]
        here = checkout_map.checkouts(dirs)
        planned: list[_Planned] = []
        for local in locals_:
            writer = self._writers.get(local.agent_type)
            if writer is None:
                continue
            status = writer.status(local.config_dir)
            report.writers[local.agent_type] = status
            if not status.ok:
                continue
            targets = targets_for(
                local.agent_type,
                writer,
                hub,
                machine=self._machine(),
                checkouts=here,
                home=self._home(),
                codex_imports_claude=bool(ledger.codex_imports_claude),
            )
            report.held_back[local.agent_type] = targets.held_back
            planned.append(
                _Planned(local, writer, targets, plan_agent(writer, local, targets, ledger))
            )
        return planned

    async def _record(self, event: AuditEventType, actor: str, report: SyncReport) -> None:
        if not report.changed():
            return
        await self._audit.record(event.value, actor=actor, details=report.details())


def planned_globals(planned: Sequence[_Planned]) -> dict[str, int]:
    return {p.local.agent_type: len(p.targets.globals) for p in planned if p.targets.globals}


def _locals(agents: Sequence[AgentSource]) -> list[LocalAgent]:
    return [LocalAgent(a.agent, a.agent_type, a.config_dir) for a in agents]


def _op_key(op: CopyOp) -> tuple[str, str, str, str]:
    return (op.agent, op.action, op.path, op.entry)


def _summary(changes: Any) -> str:
    parts = []
    if changes.upserts:
        parts.append(f"{len(changes.upserts)} published")
    if changes.deletes:
        parts.append(f"{len(changes.deletes)} removed")
    return "Memory sync: " + ", ".join(parts)


__all__ = ["AgentLister", "AuditPort", "MemorySyncService"]
