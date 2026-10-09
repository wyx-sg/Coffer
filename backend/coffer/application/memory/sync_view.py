"""What the Memory page reads about the sync, and **Curate now** (spec memory
"Manage memory sync in the web UI and on the command line", "Show each agent's
own curation and ask it to curate now").

Read-only views over the hub, the ledger and the agents' own settings, plus
the one action that asks an agent to curate its own memory.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from coffer.application.memory.sync_report import preview_summary
from coffer.application.memory.sync_service import AuditPort, MemorySyncService
from coffer.application.memory.sync_write import LocalAgent
from coffer.domain.audit import AuditEventType
from coffer.domain.memory.hub import CLAUDE_CODE, CODEX, HubEntry, project_folder
from coffer.domain.memory.sync_plan import STATE_WRITTEN
from coffer.infrastructure.memory import checkouts as checkout_map
from coffer.infrastructure.memory.curation import CurationState, curation_state

#: A copy's state on the page, per local agent.
COPY_ORIGIN = "origin"
COPY_HELD_BACK = "held_back"
COPY_DEFERRED = "deferred"
COPY_RULES = "rules"
COPY_PENDING = "pending"

Launch = Callable[[str, str, str], Awaitable[bool]]


@dataclass(frozen=True)
class AgentRow:
    agent: str
    agent_type: str
    writer: dict[str, str]
    curation: CurationState
    copies: dict[str, int]


@dataclass(frozen=True)
class ProjectRow:
    key: str
    folder: str
    memories: int
    agents: dict[str, int]
    checked_out: str | None


@dataclass(frozen=True)
class SyncState:
    running: bool
    last_synced_at: str
    last_report: dict[str, Any]
    preview: dict[str, Any] | None
    codex_imports_claude: bool | None
    agents: list[AgentRow]
    projects: list[ProjectRow]
    global_memories: int
    machine: str


@dataclass(frozen=True)
class EntryRow:
    entry: HubEntry
    #: ``agent type → copy state`` on this machine.
    copies: dict[str, str] = field(default_factory=dict)


class MemorySyncView:
    def __init__(
        self,
        service: MemorySyncService,
        *,
        machine: Callable[[], str],
        home: Callable[[], str],
        audit: AuditPort,
        launch: Launch,
    ) -> None:
        self._svc = service
        self._machine = machine
        self._home = home
        self._audit = audit
        self._launch = launch

    async def _checkouts(self, agents: list[LocalAgent]) -> dict[str, str]:
        dirs = [d for a in agents for d in checkout_map.recorded_dirs(a.agent_type, a.config_dir)]
        return checkout_map.checkouts(dirs)

    async def state(self) -> SyncState:
        agents = await self._svc.local_agents()
        ledger = self._svc.ledger.load()
        hub = self._svc.hub.entries()
        here = await self._checkouts(agents)
        pending = self._svc.previews.load()
        rows = []
        for a in agents:
            writer = self._svc.writers.get(a.agent_type)
            status = writer.status(a.config_dir) if writer else None
            states = Counter(r.state for r in ledger.agent_copies(a.key).values())
            rows.append(
                AgentRow(
                    agent=a.agent,
                    agent_type=a.agent_type,
                    writer={"state": status.state, "path": status.path, "reason": status.reason}
                    if status
                    else {"state": "unsupported", "path": "", "reason": ""},
                    curation=curation_state(a.agent_type, a.config_dir),
                    copies=dict(states),
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
        )

    async def entries(self, project: str) -> list[EntryRow]:
        """The hub's memories for one project (``""`` for global), each with
        where it was written on this machine."""
        agents = await self._svc.local_agents()
        ledger = self._svc.ledger.load()
        here = await self._checkouts(agents)
        machine = self._machine()
        by_entry: dict[str, dict[str, str]] = defaultdict(dict)
        for a in agents:
            for rec in ledger.agent_copies(a.key).values():
                current = by_entry[rec.entry].get(a.agent_type)
                if current != STATE_WRITTEN:
                    by_entry[rec.entry][a.agent_type] = rec.state
        out = []
        for entry in sorted(
            self._svc.hub.entries().values(), key=lambda e: e.updated_at, reverse=True
        ):
            if entry.project != project:
                continue
            copies = {}
            for a in agents:
                copies[a.agent_type] = _copy_state(
                    entry, a, machine, here, by_entry, ledger.codex_imports_claude
                )
            out.append(EntryRow(entry=entry, copies=copies))
        return out

    async def curate(self, agent_type: str, actor: str) -> bool:
        """Start the agent headless with the curation prompt ("Curate now")."""
        agents = [a for a in await self._svc.local_agents() if a.agent_type == agent_type]
        if not agents:
            return False
        local = agents[0]
        started = await self._launch(local.agent_type, local.config_dir, self._home())
        await self._audit.record(
            AuditEventType.MEMORY_CURATION_REQUESTED.value,
            actor=actor,
            details={"agent": local.agent, "agent_type": local.agent_type, "started": started},
        )
        return started


def _copy_state(
    entry: HubEntry,
    agent: LocalAgent,
    machine: str,
    here: Mapping[str, str],
    copies: Mapping[str, Mapping[str, str]],
    codex_imports: bool | None,
) -> str:
    if entry.origin.machine == machine and entry.origin.agent == agent.agent_type:
        return COPY_ORIGIN
    if agent.agent_type == CODEX and entry.origin.agent == CLAUDE_CODE and codex_imports:
        return COPY_DEFERRED
    if entry.project and entry.project not in here:
        return COPY_HELD_BACK
    state = copies.get(entry.id, {}).get(agent.agent_type)
    if state:
        return state
    if not entry.project and agent.agent_type == CLAUDE_CODE:
        return COPY_RULES
    return COPY_PENDING


__all__ = [
    "COPY_DEFERRED",
    "COPY_HELD_BACK",
    "COPY_ORIGIN",
    "COPY_PENDING",
    "COPY_RULES",
    "AgentRow",
    "EntryRow",
    "MemorySyncView",
    "ProjectRow",
    "SyncState",
]
