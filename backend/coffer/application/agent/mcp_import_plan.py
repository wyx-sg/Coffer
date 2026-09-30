"""Plan an import of agents' direct MCP entries into Coffer — a dry run.

Spec agent-registry "Plan an import of agents' direct MCP entries". The person
picks entries from the agents' own config files; the plan says, without writing
anything, what importing them would do:

- **servers** — one per distinct server. An entry whose transport a server
  Coffer already has matches is a *duplicate* (only the entry goes, and the
  agent then reaches that server through Coffer, so it joins the server's reach
  when the server is scoped). Entries sharing one transport across agents
  *merge* into one new server, reaching the agents that had it.
- **files** — per agent config file that changes, unified-diff hunks against
  the file's real text and what removing the entries would write, redacted.
- **coffer_entry_changes** — any difference the reconciler's ``mcp_entry``
  target already has pending for those agents: Coffer's own entry is how they
  will reach the imported servers.

Every planned write is also stated in the reconciler's vocabulary
(``Difference`` / ``Item`` / ``PlannedChange``, with the same safe JSON text),
so the plan reads like any other change preview. Pure: reads files and rows,
writes nothing.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Mapping, Sequence
from typing import Protocol

from coffer.application.agent.config_file_service import ConfigFileStorePort
from coffer.application.agent.mcp_entry_service import AgentMcpEntryService, container_key
from coffer.application.agent.mcp_import_types import (
    TARGET,
    ImportChoice,
    ImportPlan,
    PlannedAgent,
    PlannedEntry,
    PlannedFile,
    PlannedServer,
    display_path,
    safe_params,
    safe_text,
)
from coffer.application.agent.mcp_reconcile import TARGET as MCP_ENTRY_TARGET
from coffer.application.reconcile.reconciler import Reconciler
from coffer.domain.agent.config_diff import (
    diff_hunks,
    entry_secret_literals,
    normalise_server_name,
    server_name_usable,
)
from coffer.domain.agent.config_files import ConfigFileSpec
from coffer.domain.agent.mcp_entries import (
    McpEntry,
    matches_transport,
    parse_entries,
    remove_entry,
    secret_env_keys,
)
from coffer.domain.agent.mcp_injection import default_container_key
from coffer.domain.agent.types import AgentType, agent_display_name
from coffer.domain.errors import CofferError, ResourceNotFound
from coffer.domain.reconcile import (
    Decision,
    Difference,
    Disposition,
    Item,
    ItemResult,
    Op,
    PlannedChange,
    Subject,
)
from coffer.domain.resource import Resource


class _Resources(Protocol):
    async def list(
        self, kind: str | None = None, enabled: bool | None = None
    ) -> list[Resource]: ...


def _identity(entry: McpEntry) -> tuple[str, ...]:
    if entry.transport == "stdio":
        return ("stdio", entry.command or "", *entry.args)
    return ("http", entry.url or "")


def _unique(base: str, taken: set[str]) -> str:
    name, n = base, 2
    while name in taken:
        name = f"{base}-{n}"
        n += 1
    taken.add(name)
    return name


class McpImportPlanner:
    def __init__(
        self,
        *,
        entries: AgentMcpEntryService,
        store: ConfigFileStorePort,
        resources: _Resources,
        reconciler: Reconciler | None = None,
    ) -> None:
        self._entries = entries
        self._store = store
        self._rs = resources
        self._reconciler = reconciler

    async def _locate(self, choice: ImportChoice) -> tuple[PlannedEntry, ConfigFileSpec | None]:
        try:
            agent, _cfg = await self._entries.agent(choice.agent_uid)
        except ResourceNotFound:
            return PlannedEntry(
                choice.agent_uid, "", choice.name, choice.source, None, "unavailable",
                error_code="AGENT_NOT_FOUND", error="The agent is not registered.",
            ), None  # fmt: skip
        try:
            spec, _text, parsed = await self._entries.locate(
                choice.agent_uid, choice.name, choice.source
            )
        except CofferError as e:
            return PlannedEntry(
                agent.uid, agent.name, choice.name, choice.source, None, "unavailable",
                error_code=e.code, error=str(e),
            ), None  # fmt: skip
        keys = tuple(secret_env_keys({**parsed.env, **parsed.headers}))
        refs = {k: f"mcp/{agent.name}/{parsed.name}/{k}" for k in keys}
        return PlannedEntry(
            agent.uid, agent.name, parsed.name, spec.key, str(spec.path), "source",
            transport=parsed.transport, secret_keys=keys, secret_refs=refs, entry=parsed,
        ), spec  # fmt: skip

    async def plan(self, choices: Sequence[ImportChoice]) -> ImportPlan:
        registered = [
            (r, t)
            for r in await self._rs.list(kind="mcp_server")
            if isinstance(t := r.config.get("transport"), Mapping)
        ]
        taken = {r.name for r, _ in registered}
        located: list[tuple[ImportChoice, PlannedEntry, ConfigFileSpec | None]] = []
        seen: set[tuple[str, str, str | None]] = set()
        for choice in choices:
            planned, spec = await self._locate(choice)
            key = (planned.agent_uid, planned.name, planned.source)
            if key in seen:
                continue
            seen.add(key)
            located.append((choice, planned, spec))

        unavailable = [p for _c, p, _s in located if p.role == "unavailable"]
        groups: dict[tuple[str, ...], list[tuple[ImportChoice, PlannedEntry]]] = {}
        duplicates: dict[str, list[PlannedEntry]] = {}
        for choice, planned, _spec in located:
            if planned.entry is None:
                continue
            match = next((r for r, t in registered if matches_transport(planned.entry, t)), None)
            if match is not None:
                duplicates.setdefault(match.uid, []).append(
                    dataclasses.replace(planned, role="duplicate")
                )
                continue
            groups.setdefault(_identity(planned.entry), []).append((choice, planned))

        servers: list[PlannedServer] = []
        for members in groups.values():
            servers.append(self._add_server(members, taken))
        by_uid = {r.uid: r for r, _ in registered}
        for uid, entries in duplicates.items():
            servers.append(self._duplicate_server(by_uid[uid], entries))

        types: dict[str, AgentType] = {}
        for _c, p, spec in located:
            if spec is not None and p.agent_uid not in types:
                types[p.agent_uid] = (await self._entries.agent(p.agent_uid))[1].type
        files = await asyncio.to_thread(self._files, servers, located, types)
        agents = await self._agents(servers)
        pending = await self._pending_coffer_changes({a.uid for a in agents})
        return ImportPlan(
            servers=tuple(servers),
            files=tuple(files),
            agents=tuple(agents),
            unavailable=tuple(unavailable),
            coffer_entry_changes=pending,
        )

    def _add_server(
        self, members: list[tuple[ImportChoice, PlannedEntry]], taken: set[str]
    ) -> PlannedServer:
        _first_choice, first = members[0]
        assert first.entry is not None
        wanted = next((c.new_name for c, _ in members if c.new_name), None)
        base = wanted or normalise_server_name(first.name)
        name = _unique(base, taken)
        entries = (first, *(dataclasses.replace(p, role="merged") for _, p in members[1:]))
        reach = tuple(dict.fromkeys(p.agent_uid for p in entries))
        differ = any(
            (p.entry.env, p.entry.headers) != (first.entry.env, first.entry.headers)
            for p in entries[1:]
            if p.entry is not None
        )
        literals = entry_secret_literals([p.entry for p in entries if p.entry is not None])
        params = safe_params(first.entry, literals)
        merged = len(entries) > 1
        key = f"server:{name}"
        change = PlannedChange(
            Difference(
                TARGET,
                key,
                Op.ADD,
                Item(key, Subject("mcp_server", None, name), params, None, safe_text(params)),
                None,
            ),
            Decision(
                Disposition.REPAIR,
                "import_merge" if merged else "import_add",
                "The same server in several agents becomes one server in Coffer."
                if merged
                else "The entry becomes a server in Coffer, available to the agent that had it.",
            ),
        )  # fmt: skip
        return PlannedServer(
            op="add",
            name=name,
            original_name=first.name if name != first.name else None,
            name_usable=server_name_usable(name),
            resource_uid=None,
            transport=first.entry.transport,
            reach_agent_uids=reach,
            reaches_all=False,
            entries=entries,
            settings_differ=differ,
            change=change,
        )

    def _duplicate_server(self, resource: Resource, entries: list[PlannedEntry]) -> PlannedServer:
        scoped = resource.scope is not None and resource.scope.agents is not None
        current = set(resource.scope.agents or []) if scoped and resource.scope else set()
        add = tuple(
            dict.fromkeys(p.agent_uid for p in entries if scoped and p.agent_uid not in current)
        )
        transport = str(resource.config.get("transport", {}).get("type", "stdio"))
        params = {"reach_add_agents": list(add), "scoped": scoped}
        change = PlannedChange(
            Difference(
                TARGET,
                f"server:{resource.name}",
                Op.MODIFY if add else Op.ADD,
                Item(f"server:{resource.name}", Subject("mcp_server", resource.uid, resource.name),
                     params, None, safe_text(params)),
                None,
            ),
            Decision(
                Disposition.REPAIR,
                "import_duplicate",
                "Already in Coffer — only the duplicate entry is removed.",
            ),
        )  # fmt: skip
        return PlannedServer(
            op="duplicate",
            name=resource.name,
            original_name=None,
            name_usable=True,
            resource_uid=resource.uid,
            transport="http" if transport == "http" else "stdio",
            reach_agent_uids=add,
            reaches_all=not scoped,
            entries=tuple(entries),
            settings_differ=False,
            change=change,
        )

    def _files(
        self,
        servers: Sequence[PlannedServer],
        located: Sequence[tuple[ImportChoice, PlannedEntry, ConfigFileSpec | None]],
        types: Mapping[str, AgentType],
    ) -> list[PlannedFile]:
        specs = {(p.agent_uid, s.key): s for _c, p, s in located if s is not None}
        removals: dict[tuple[str, str], list[PlannedEntry]] = {}
        for server in servers:
            for p in server.entries:
                if p.source is not None:
                    removals.setdefault((p.agent_uid, p.source), []).append(p)
        out: list[PlannedFile] = []
        for (agent_uid, source), entries in removals.items():
            spec = specs[(agent_uid, source)]
            before = self._store.read_text(spec.path) or ""
            agent_type = types[agent_uid]
            ck = container_key(agent_type)
            after = before
            for p in entries:
                after = remove_entry(spec.format, after, p.name, container_key=ck)
            try:
                everything = parse_entries(spec.format, before, source=source, container_key=ck)
            except CofferError:
                everything = []
            literals = entry_secret_literals(everything)
            hunks, added, removed = diff_hunks(
                before, after, literals=literals, section=ck or default_container_key(spec.format)
            )
            changes = tuple(
                PlannedChange(
                    Difference(
                        TARGET,
                        f"entry:{agent_uid}:{source}:{p.name}",
                        Op.REMOVE,
                        None,
                        Item(
                            f"entry:{agent_uid}:{source}:{p.name}",
                            Subject("agent", agent_uid, p.agent_name),
                            params := safe_params(p.entry, literals) if p.entry else {},
                            str(spec.path),
                            safe_text(params),
                        ),
                    ),
                    Decision(
                        Disposition.REPAIR,
                        "import_remove_entry",
                        "The entry is removed from the agent's file; the agent reaches the "
                        "server through Coffer.",
                    ),
                )
                for p in entries
            )
            out.append(
                PlannedFile(
                    agent_uid=agent_uid,
                    agent_type=agent_type.value,
                    source=source,
                    path=str(spec.path),
                    display_path=display_path(str(spec.path)),
                    entries_removed=tuple(p.name for p in entries),
                    added_lines=added,
                    removed_lines=removed,
                    hunks=hunks,
                    changes=changes,
                )
            )
        return out

    async def _agents(self, servers: Sequence[PlannedServer]) -> list[PlannedAgent]:
        removed: dict[str, list[str]] = {}
        for s in servers:
            for p in s.entries:
                removed.setdefault(p.agent_uid, []).append(p.name)
        out: list[PlannedAgent] = []
        for uid, names in removed.items():
            agent, cfg = await self._entries.agent(uid)
            connected = False
            for spec in self._entries.source_specs(cfg):
                text = self._store.read_text(spec.path)
                if not text:
                    continue
                try:
                    parsed = parse_entries(
                        spec.format, text, source=spec.key, container_key=container_key(cfg.type)
                    )
                except CofferError:
                    continue
                connected = connected or any(e.is_coffer for e in parsed)
            out.append(
                PlannedAgent(
                    uid=uid,
                    name=agent.name,
                    display_name=agent_display_name(agent.config, agent.name),
                    agent_type=cfg.type.value,
                    connected=connected,
                    entries_removed=tuple(names),
                )
            )
        return out

    async def _pending_coffer_changes(self, agent_uids: set[str]) -> tuple[ItemResult, ...]:
        if self._reconciler is None or MCP_ENTRY_TARGET not in self._reconciler.target_names:
            return ()
        report = await self._reconciler.plan(targets=[MCP_ENTRY_TARGET])
        return tuple(r for r in report.results if r.change.difference.subject.uid in agent_uids)


__all__ = [
    "TARGET",
    "ImportChoice",
    "ImportPlan",
    "McpImportPlanner",
    "PlannedAgent",
    "PlannedEntry",
    "PlannedFile",
    "PlannedServer",
    "display_path",
]
