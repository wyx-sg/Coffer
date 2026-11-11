"""The rows the Memory page reads (spec memory "Manage memory sync in the web
UI and on the command line"): the sync's state, each agent, each project, each
memory with its copy state per local agent, and one memory with its text."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from coffer.application.memory.sync_locations import LocationRow
from coffer.domain.memory.hub import HubEntry
from coffer.infrastructure.memory.curation import CurationState


@dataclass(frozen=True)
class AgentRow:
    agent: str
    agent_type: str
    #: The first location that cannot be written, else the first location's.
    writer: dict[str, str]
    curation: CurationState
    #: Summed over the locations.
    copies: dict[str, int]
    locations: list[LocationRow] = field(default_factory=list)


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
    #: or the project's ``MEMORY.md``; ``""`` when there is none here.
    path: str = ""


@dataclass(frozen=True)
class EntryDetail:
    """One memory with its text (paths expanded for this machine) and, per
    local agent, where it is held."""

    entry: HubEntry
    body: str
    copies: list[CopyLocation]


__all__ = ["AgentRow", "CopyLocation", "EntryDetail", "EntryRow", "ProjectRow", "SyncState"]
