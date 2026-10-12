"""What the Memory page reads about the sync, and **Curate now** (spec memory
"Manage memory sync in the web UI and on the command line", "Show each agent's
own curation and ask it to curate now").

Read-only views over the hub, the ledger and the agents' own settings, plus
the one action that asks an agent to curate its own memory.
"""

from __future__ import annotations

import pathlib
from collections import Counter, defaultdict
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from coffer.application.memory.sync_report import preview_summary
from coffer.application.memory.sync_service import AuditPort, MemorySyncService
from coffer.application.memory.sync_write import LocalAgent
from coffer.domain.audit import AuditEventType
from coffer.domain.memory.hub import CLAUDE_CODE, CODEX, HubEntry, project_folder
from coffer.domain.memory.portable import from_portable
from coffer.domain.memory.sync_plan import STATE_WRITTEN
from coffer.infrastructure.memory import checkouts as checkout_map
from coffer.infrastructure.memory.curation import CurationState, curation_state
from coffer.infrastructure.memory.writers.claude_code import rules_path

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


@dataclass(frozen=True)
class CopyLocation:
    """Where one local agent holds a memory: its copy's state and file."""

    agent_type: str
    state: str
    #: The file on this machine: the agent's own (the origin), Coffer's copy,
    #: or the rules file; ``""`` when there is none here.
    path: str = ""


@dataclass(frozen=True)
class EntryDetail:
    """One memory with its text (paths expanded for this machine) and, per
    local agent, where it is held."""

    entry: HubEntry
    body: str
    copies: list[CopyLocation]


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

    async def _copies_by_entry(
        self, agents: list[LocalAgent]
    ) -> dict[str, dict[str, tuple[str, str]]]:
        """``entry id → agent type → (state, path)`` from the ledger; a
        written copy wins over any other record of the same entry."""
        ledger = self._svc.ledger.load()
        out: dict[str, dict[str, tuple[str, str]]] = defaultdict(dict)
        for a in agents:
            for path, rec in ledger.agent_copies(a.key).items():
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
        out = []
        for entry in sorted(
            self._svc.hub.entries().values(), key=lambda e: e.updated_at, reverse=True
        ):
            if entry.project != project:
                continue
            copies = {
                a.agent_type: _copy_state(entry, a, machine, here, states, imports) for a in agents
            }
            out.append(EntryRow(entry=entry, copies=copies))
        return out

    async def entry(self, entry_id: str) -> EntryDetail | None:
        """One memory's text and, per local agent, its copy's state and file
        ("Manage memory sync in the web UI and on the command line")."""
        entry = self._svc.hub.entries().get(entry_id)
        if entry is None:
            return None
        agents = await self._svc.local_agents()
        imports = self._svc.ledger.load().codex_imports_claude
        here = await self._checkouts(agents)
        machine = self._machine()
        held = (await self._copies_by_entry(agents)).get(entry.id, {})
        states = {entry.id: {t: v[0] for t, v in held.items()}}
        copies = []
        for a in agents:
            state = _copy_state(entry, a, machine, here, states, imports)
            copies.append(
                CopyLocation(
                    agent_type=a.agent_type,
                    state=state,
                    path=_copy_path(entry, a, state, held.get(a.agent_type)),
                )
            )
        body = from_portable(entry.body, repo_root=here.get(entry.project), home=self._home())
        return EntryDetail(entry=entry, body=body, copies=copies)

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


def _copy_path(entry: HubEntry, agent: LocalAgent, state: str, held: tuple[str, str] | None) -> str:
    """The file that holds ``entry`` in ``agent`` here, if any."""
    if state == COPY_ORIGIN:
        source = entry.origin.source
        if agent.agent_type == CLAUDE_CODE:
            return str(pathlib.Path(agent.config_dir) / f"{source}.md")
        return str(pathlib.Path(agent.config_dir) / source.split("::", 1)[0])
    if state == COPY_RULES:
        return str(rules_path(agent.config_dir))
    if held is not None:
        return held[1]
    return ""


__all__ = [
    "COPY_DEFERRED",
    "COPY_HELD_BACK",
    "COPY_ORIGIN",
    "COPY_PENDING",
    "COPY_RULES",
    "AgentRow",
    "CopyLocation",
    "EntryDetail",
    "EntryRow",
    "MemorySyncView",
    "ProjectRow",
    "SyncState",
]
