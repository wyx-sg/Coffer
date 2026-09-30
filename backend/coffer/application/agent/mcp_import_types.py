"""The data an import plan carries (``mcp_import_plan``), and its safe renderings.

Split out of the planner for the file-size budget. No secret value is held in
anything a surface renders: ``PlannedEntry.entry`` (the parsed entry, values
included) is ``repr=False`` and never put on the wire.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from coffer.domain.agent.config_diff import DiffHunk, redact_line
from coffer.domain.agent.mcp_entries import McpEntry
from coffer.domain.reconcile import ItemResult, PlannedChange

TARGET = "mcp_import"


@dataclass(frozen=True)
class ImportChoice:
    agent_uid: str
    name: str
    source: str | None = None
    #: The name the server it creates takes, instead of the normalised entry name.
    new_name: str | None = None


@dataclass(frozen=True)
class PlannedEntry:
    """One chosen entry and what happens to it."""

    agent_uid: str
    agent_name: str
    name: str
    source: str | None
    path: str | None
    #: ``source``: its server is added from it; ``merged``: same transport as
    #: another chosen entry, removed; ``duplicate``: a server Coffer has already,
    #: removed; ``unavailable``: cannot be imported (``error`` says why).
    role: Literal["source", "merged", "duplicate", "unavailable"]
    transport: Literal["stdio", "http"] | None = None
    secret_keys: tuple[str, ...] = ()
    #: Where each secret value moves: ``mcp/<agent>/<entry>/<KEY>``.
    secret_refs: Mapping[str, str] = field(default_factory=dict)
    error_code: str | None = None
    error: str | None = None
    entry: McpEntry | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class PlannedServer:
    op: Literal["add", "duplicate"]
    name: str
    #: The entry's own name, when normalising or de-duplicating changed it.
    original_name: str | None
    name_usable: bool
    #: duplicate: the existing server's uid.
    resource_uid: str | None
    transport: Literal["stdio", "http"]
    #: add: the agents that had it. duplicate: the agents to add to its reach.
    reach_agent_uids: tuple[str, ...]
    #: duplicate: the existing server already reaches every agent.
    reaches_all: bool
    entries: tuple[PlannedEntry, ...]
    #: Merged entries whose environment or headers differ (the first one's win).
    settings_differ: bool
    change: PlannedChange


@dataclass(frozen=True)
class PlannedFile:
    agent_uid: str
    agent_type: str
    source: str
    path: str
    display_path: str
    entries_removed: tuple[str, ...]
    added_lines: int
    removed_lines: int
    hunks: tuple[DiffHunk, ...]
    changes: tuple[PlannedChange, ...]
    op: Literal["modify"] = "modify"


@dataclass(frozen=True)
class PlannedAgent:
    uid: str
    name: str
    display_name: str
    agent_type: str
    #: Whether its config already holds Coffer's own entry.
    connected: bool
    entries_removed: tuple[str, ...]


@dataclass(frozen=True)
class ImportPlan:
    servers: tuple[PlannedServer, ...]
    files: tuple[PlannedFile, ...]
    agents: tuple[PlannedAgent, ...]
    unavailable: tuple[PlannedEntry, ...]
    coffer_entry_changes: tuple[ItemResult, ...]

    @property
    def changes(self) -> tuple[PlannedChange, ...]:
        return tuple(s.change for s in self.servers) + tuple(
            c for f in self.files for c in f.changes
        )


def safe_text(params: Mapping[str, Any]) -> str:
    return json.dumps(params, indent=2, sort_keys=True)


def display_path(path: str) -> str:
    home = str(Path.home())
    return "~" + path[len(home) :] if path == home or path.startswith(home + "/") else path


def safe_params(entry: McpEntry, literals: Sequence[str]) -> dict[str, Any]:
    """The entry as the plan may show it: no secret value, keys named only."""
    base: dict[str, Any] = {"transport": entry.transport}
    if entry.transport == "stdio":
        base["command"] = entry.command
        base["args"] = [redact_line(a, literals) for a in entry.args]
        base["env_keys"] = sorted(entry.env)
    else:
        base["url"] = redact_line(entry.url or "", literals)
        base["header_keys"] = sorted(entry.headers)
    return base
