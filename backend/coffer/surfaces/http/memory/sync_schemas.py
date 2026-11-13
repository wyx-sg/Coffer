"""The wire shapes of ``/api/v1/memory/sync/*`` (spec memory "Manage memory
sync in the web UI and on the command line")."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WriterStatusOut(BaseModel):
    state: str
    path: str = ""
    reason: str = ""


class SyncLocationOut(BaseModel):
    """One place the agent's writer writes into (Codex: one per memory folder)."""

    #: ``""`` for the agent's first location, else the folder's name.
    name: str = ""
    path: str
    writer: WriterStatusOut
    #: How many copies this machine holds in this location, by state.
    copies: dict[str, int] = Field(default_factory=dict)


class SyncAgentOut(BaseModel):
    agent: str
    agent_type: str
    #: The first location that cannot be written, else the first location's.
    writer: WriterStatusOut
    #: How many copies this machine holds in the agent, by state, summed over
    #: its locations.
    copies: dict[str, int] = Field(default_factory=dict)
    locations: list[SyncLocationOut] = Field(default_factory=list)


class SyncProjectOut(BaseModel):
    key: str
    folder: str
    memories: int
    #: How many of the project's memories each agent type published.
    agents: dict[str, int] = Field(default_factory=dict)
    #: The project's checkout on this machine, or ``null`` (held back).
    checked_out: str | None = None


class MemorySyncStateOut(BaseModel):
    running: bool
    last_synced_at: str = ""
    last_report: dict[str, Any] = Field(default_factory=dict)
    preview: dict[str, Any] | None = None
    codex_imports_claude: bool | None = None
    agents: list[SyncAgentOut] = Field(default_factory=list)
    projects: list[SyncProjectOut] = Field(default_factory=list)
    machine: str = ""


class MemorySyncReportOut(BaseModel):
    """What one sync, write or undo did (the ``memory_synced`` details)."""

    details: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)


class HubEntryOut(BaseModel):
    id: str
    title: str
    description: str
    type: str
    project: str = ""
    origin_machine: str
    origin_agent: str
    created_at: str
    updated_at: str
    #: ``agent type → copy state`` on this machine (``written``, ``edited``,
    #: ``removed``, ``held_back``, ``deferred``, ``block``, ``over_limit``,
    #: ``origin``, ``pending``).
    copies: dict[str, str] = Field(default_factory=dict)


class HubEntryListOut(BaseModel):
    project: str
    entries: list[HubEntryOut] = Field(default_factory=list)


class EntryCopyOut(BaseModel):
    agent_type: str
    #: The copy's state here (as in ``HubEntryOut.copies``).
    state: str
    #: The file that holds the memory in this agent here; ``""`` when none.
    path: str = ""


class HubEntryDetailOut(BaseModel):
    """One memory with its text and, per local agent, where it is held."""

    id: str
    title: str
    description: str
    type: str
    project: str = ""
    origin_machine: str
    origin_agent: str
    created_at: str
    updated_at: str
    #: The memory's text, its paths expanded for this machine. Read only.
    body: str
    copies: list[EntryCopyOut] = Field(default_factory=list)


class CodexImportIn(BaseModel):
    #: ``true`` when Codex imports Claude Code's memories itself, ``null`` to forget.
    value: bool | None = None


__all__ = [
    "CodexImportIn",
    "EntryCopyOut",
    "HubEntryDetailOut",
    "HubEntryListOut",
    "HubEntryOut",
    "MemorySyncReportOut",
    "MemorySyncStateOut",
    "SyncAgentOut",
    "SyncProjectOut",
    "WriterStatusOut",
]
