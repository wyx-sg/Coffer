"""What the Memory page reads about the sync, and **Curate now** (spec memory
"Manage memory sync in the web UI and on the command line", "Show each agent's
own curation and ask it to curate now").

Read-only views over the hub, the ledger and the agents' own settings, plus
the two actions on an agent's own curation: ask it to curate now, and turn it
on when the person asks.
"""

from __future__ import annotations

import asyncio
import pathlib
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping

from coffer.application.memory.sync_locations import (
    LocationRow,
    agent_copies_everywhere,
    location_rows,
    summed,
)
from coffer.application.memory.sync_prompts import claude_curation_prompt, sort_prompt
from coffer.application.memory.sync_report import preview_summary
from coffer.application.memory.sync_rows import (
    AgentRow,
    CopyLocation,
    EntryDetail,
    EntryRow,
    ProjectRow,
    SyncState,
)
from coffer.application.memory.sync_service import (
    AuditPort,
    MemorySyncService,
    task_material_ids,
    to_sort_ids,
)
from coffer.application.memory.sync_write import LocalAgent
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ResourceNotFound
from coffer.domain.memory.hub import CLAUDE_CODE, CODEX, HubEntry, project_folder
from coffer.domain.memory.portable import from_portable
from coffer.domain.memory.sync_plan import STATE_WRITTEN
from coffer.infrastructure.memory import checkouts as checkout_map
from coffer.infrastructure.memory.curation import curation_state, enable_curation
from coffer.infrastructure.memory.sorted_store import SortedRecord
from coffer.infrastructure.memory.writers.claude_code import (
    memory_dir,
    rules_path,
)

#: A copy's state on the page, per local agent.
COPY_ORIGIN = "origin"
COPY_HELD_BACK = "held_back"
COPY_DEFERRED = "deferred"
COPY_RULES = "rules"
#: Written as text into the project's ``MEMORY.md`` block (Claude Code).
COPY_BLOCK = "block"
#: Task material another agent filed: it stays with that agent until sorted.
COPY_STAYS_HOME = "stays_home"
COPY_PENDING = "pending"
#: How many waiting memories the sort hand-off lists by name.
SORT_PROMPT_MAX = 60


class MemorySyncView:
    def __init__(
        self,
        service: MemorySyncService,
        *,
        machine: Callable[[], str],
        home: Callable[[], str],
        audit: AuditPort,
    ) -> None:
        self._svc = service
        self._machine = machine
        self._home = home
        self._audit = audit

    async def _checkouts(self, agents: list[LocalAgent]) -> dict[str, str]:
        # Walks each agent's projects tree and probes every repository: blocking
        # filesystem work, kept off the daemon's event loop.
        def scan() -> dict[str, str]:
            dirs = [
                d for a in agents for d in checkout_map.recorded_dirs(a.agent_type, a.config_dir)
            ]
            return checkout_map.checkouts(dirs)

        return await asyncio.to_thread(scan)

    async def state(self) -> SyncState:
        agents = await self._svc.local_agents()
        # The ledger, hub and preview are files on disk: read them off the loop.
        ledger, hub, pending, sortings = await asyncio.to_thread(
            lambda: (
                self._svc.ledger.load(),
                self._svc.hub.entries(),
                self._svc.previews.load(),
                self._svc.sortings.records(),
            )
        )
        here = await self._checkouts(agents)
        rows = []
        for a in agents:
            writer = self._svc.writers.get(a.agent_type)
            locations = location_rows(writer, a, ledger) if writer is not None else []
            writer_state, copies = summed(locations)
            rows.append(
                AgentRow(
                    agent=a.agent,
                    agent_type=a.agent_type,
                    writer=writer_state,
                    curation=curation_state(a.agent_type, a.config_dir),
                    copies=copies,
                    locations=locations,
                )
            )
        by_project: dict[str, Counter[str]] = defaultdict(Counter)
        globals_ = 0
        for entry in hub.values():
            if entry.project:
                by_project[entry.project][entry.origin.agent] += 1
            else:
                globals_ += 1
        projects = [
            ProjectRow(
                key=key,
                folder=project_folder(key),
                memories=sum(c.values()),
                agents=dict(c),
                checked_out=here.get(key),
            )
            for key, c in sorted(by_project.items())
        ]
        preview = None
        if pending is not None:
            preview = {"created_at": pending[0], **preview_summary(pending[1], {})}
        return SyncState(
            running=self._svc.running,
            last_synced_at=ledger.last_synced_at,
            last_report=ledger.last_report,
            preview=preview,
            codex_imports_claude=ledger.codex_imports_claude,
            agents=rows,
            projects=projects,
            global_memories=globals_,
            machine=self._machine(),
            to_sort=len(to_sort_ids(hub, sortings)),
        )

    async def _copies_by_entry(
        self, agents: list[LocalAgent]
    ) -> dict[str, dict[str, tuple[str, str]]]:
        """``entry id → agent type → (state, path)`` from the ledger; a
        written copy wins over any other record of the same entry."""
        ledger = self._svc.ledger.load()
        out: dict[str, dict[str, tuple[str, str]]] = defaultdict(dict)
        for a in agents:
            for path, rec in agent_copies_everywhere(ledger, a).items():
                current = out[rec.entry].get(a.agent_type)
                if current is None or current[0] != STATE_WRITTEN:
                    out[rec.entry][a.agent_type] = (rec.state, path)
        return out

    async def entries(self, project: str) -> list[EntryRow]:
        """The hub's memories for one project (``""`` for global), each with
        where it was written on this machine."""
        agents = await self._svc.local_agents()
        imports = self._svc.ledger.load().codex_imports_claude
        here = await self._checkouts(agents)
        machine = self._machine()
        by_entry = await self._copies_by_entry(agents)
        states = {e: {t: v[0] for t, v in m.items()} for e, m in by_entry.items()}
        hub, sortings = await asyncio.to_thread(
            lambda: (self._svc.hub.entries(), self._svc.sortings.records())
        )
        home_only = task_material_ids(hub, sortings)
        waiting = set(to_sort_ids(hub, sortings))
        out = []
        for entry in sorted(hub.values(), key=lambda e: e.updated_at, reverse=True):
            if entry.project != project:
                continue
            copies = {
                a.agent_type: _copy_state(entry, a, machine, here, states, imports, home_only)
                for a in agents
            }
            out.append(EntryRow(entry=entry, copies=copies, to_sort=entry.id in waiting))
        return out

    async def entry(self, entry_id: str) -> EntryDetail | None:
        """One memory's text and, per local agent, its copy's state and file
        ("Manage memory sync in the web UI and on the command line")."""
        hub, sortings = await asyncio.to_thread(
            lambda: (self._svc.hub.entries(), self._svc.sortings.records())
        )
        entry = hub.get(entry_id)
        if entry is None:
            return None
        home_only = task_material_ids(hub, sortings)
        agents = await self._svc.local_agents()
        imports = self._svc.ledger.load().codex_imports_claude
        here = await self._checkouts(agents)
        machine = self._machine()
        held = (await self._copies_by_entry(agents)).get(entry.id, {})
        states = {entry.id: {t: v[0] for t, v in held.items()}}
        copies = []
        for a in agents:
            state = _copy_state(entry, a, machine, here, states, imports, home_only)
            copies.append(
                CopyLocation(
                    agent_type=a.agent_type,
                    state=state,
                    path=_copy_path(entry, a, state, held.get(a.agent_type), here),
                )
            )
        body = from_portable(entry.body, repo_root=here.get(entry.project), home=self._home())
        return EntryDetail(entry=entry, body=body, copies=copies)

    async def curation_handoff(self, agent_type: str, actor: str) -> str | None:
        """**Curate now**: the prompt that asks the agent, in a terminal the
        person watches, to consolidate the memory folders Coffer wrote copies
        into; ``None`` for an agent whose own curation needs no asking (Codex
        consolidates whenever its memories are on)."""
        if agent_type != CLAUDE_CODE:
            return None
        agents = [a for a in await self._svc.local_agents() if a.agent_type == agent_type]
        if not agents:
            return None
        local = agents[0]
        ledger = await asyncio.to_thread(self._svc.ledger.load)
        folders = sorted(
            {
                str(pathlib.Path(path).parent)
                for path, rec in ledger.agent_copies(local.key).items()
                if rec.state == STATE_WRITTEN
            }
        )
        await self._audit.record(
            AuditEventType.MEMORY_CURATION_REQUESTED.value,
            actor=actor,
            details={"agent": local.agent, "agent_type": local.agent_type, "folders": len(folders)},
        )
        return claude_curation_prompt(folders, str(rules_path(local.config_dir)))

    async def to_sort(self) -> list[HubEntry]:
        """The task material no one has sorted yet, newest first."""
        hub, sortings = await asyncio.to_thread(
            lambda: (self._svc.hub.entries(), self._svc.sortings.records())
        )
        return [hub[i] for i in to_sort_ids(hub, sortings)]

    async def sort_handoff(self, actor: str) -> str:
        """**Sort into knowledge**: the prompt that asks the person's agent, in a
        terminal they watch, to sort the waiting task material."""
        waiting = await self.to_sort()
        root = self._svc.hub.root()
        shown = waiting[:SORT_PROMPT_MAX]
        await self._audit.record(
            AuditEventType.MEMORY_SORT_REQUESTED.value,
            actor=actor,
            details={"memories": len(waiting)},
        )
        return sort_prompt(
            [(e, str(root / e.path)) for e in shown], str(root), len(waiting) - len(shown)
        )

    async def mark_sorted(
        self, entry_ids: list[str], outcome: str, where: str, actor: str
    ) -> list[str]:
        """Record that the person's agent sorted ``entry_ids``; answer the ids
        recorded. An id not in the hub is refused (``ResourceNotFound`` upstream)."""
        hub = await asyncio.to_thread(self._svc.hub.entries)
        missing = [i for i in entry_ids if i not in hub]
        if missing:
            raise ResourceNotFound(f"memory {missing[0]}")
        now = self._svc.now()
        records = [SortedRecord(i, outcome, where, now, actor) for i in dict.fromkeys(entry_ids)]
        await asyncio.to_thread(self._svc.sortings.record, records, actor)
        await self._audit.record(
            AuditEventType.MEMORY_SORTED.value,
            actor=actor,
            details={"memories": len(records), "outcome": outcome, "where": where},
        )
        return [r.id for r in records]

    async def enable_curation(self, agent_type: str, actor: str) -> bool:
        """**Turn on** the agent's own curation in its settings (Claude Code's
        Auto Dream), backed up first; answer whether a setting was written."""
        agents = [a for a in await self._svc.local_agents() if a.agent_type == agent_type]
        if not agents:
            return False
        local = agents[0]
        changed = await asyncio.to_thread(enable_curation, local.agent_type, local.config_dir)
        if changed:
            await self._audit.record(
                AuditEventType.MEMORY_CURATION_ENABLED.value,
                actor=actor,
                details={"agent": local.agent, "agent_type": local.agent_type},
            )
        return changed


def _copy_state(
    entry: HubEntry,
    agent: LocalAgent,
    machine: str,
    here: Mapping[str, str],
    copies: Mapping[str, Mapping[str, str]],
    codex_imports: bool | None,
    home_only: frozenset[str] = frozenset(),
) -> str:
    if entry.origin.machine == machine and entry.origin.agent == agent.agent_type:
        return COPY_ORIGIN
    if entry.id in home_only and entry.origin.agent != agent.agent_type:
        return COPY_STAYS_HOME
    if agent.agent_type == CODEX and entry.origin.agent == CLAUDE_CODE and codex_imports:
        return COPY_DEFERRED
    if entry.project and entry.project not in here:
        return COPY_HELD_BACK
    state = copies.get(entry.id, {}).get(agent.agent_type)
    if state:
        return state
    if agent.agent_type == CLAUDE_CODE:
        return COPY_BLOCK if entry.project else COPY_RULES
    return COPY_PENDING


def _copy_path(
    entry: HubEntry,
    agent: LocalAgent,
    state: str,
    held: tuple[str, str] | None,
    here: Mapping[str, str],
) -> str:
    """The file that holds ``entry`` in ``agent`` here, if any."""
    if state == COPY_ORIGIN:
        source = entry.origin.source
        if agent.agent_type == CLAUDE_CODE:
            return str(pathlib.Path(agent.config_dir) / f"{source}.md")
        return str(pathlib.Path(agent.config_dir) / source.split("::", 1)[0])
    if state == COPY_RULES:
        return str(rules_path(agent.config_dir))
    if state == COPY_BLOCK and entry.project in here:
        return str(memory_dir(agent.config_dir, here[entry.project]) / "MEMORY.md")
    if held is not None:
        return held[1]
    return ""


__all__ = [
    "COPY_BLOCK",
    "COPY_DEFERRED",
    "COPY_HELD_BACK",
    "COPY_ORIGIN",
    "COPY_PENDING",
    "COPY_RULES",
    "COPY_STAYS_HOME",
    "AgentRow",
    "CopyLocation",
    "EntryDetail",
    "EntryRow",
    "LocationRow",
    "MemorySyncView",
    "ProjectRow",
    "SyncState",
]
