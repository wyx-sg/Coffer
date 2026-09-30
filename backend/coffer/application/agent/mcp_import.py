"""Apply an import of agents' direct MCP entries — exactly what the plan says.

Spec agent-registry "Apply an import of agents' direct MCP entries". The plan
is recomputed here from the files as they are now, so nothing the files no
longer hold is written; each write then goes through the path that already
owns it and audits it:

1. Coffer's own entry, where the reconciler has a repairable difference
   pending for an agent involved (it is how the agent reaches what it imports).
2. Per server to add: ``AgentMcpEntryService.adopt`` on its first entry
   (secret values into the keychain under the plan's refs, register, then
   remove the entry, rolled back on failure), then its reach set to the agents
   that had it.
3. Per merged or duplicate entry: the agent joins the server's reach when the
   server is scoped, then the entry is removed from the agent's file.

One entry failing does not stop the rest; every entry comes back with its
outcome so a partial import can be reported.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from coffer.application.agent.mcp_entry_service import AgentMcpEntryService
from coffer.application.agent.mcp_import_plan import McpImportPlanner
from coffer.application.agent.mcp_import_types import (
    ImportChoice,
    ImportPlan,
    PlannedEntry,
    PlannedServer,
)
from coffer.domain.errors import CofferError
from coffer.domain.reconcile import Disposition, ItemResult
from coffer.domain.resource import Resource
from coffer.domain.scope import Scope

Outcome = Literal["added", "merged", "removed_duplicate", "failed", "skipped"]


@dataclass(frozen=True)
class EntryOutcome:
    agent_uid: str
    name: str
    source: str | None
    outcome: Outcome
    server_name: str | None = None
    resource_uid: str | None = None
    error_code: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class ImportReport:
    entries: tuple[EntryOutcome, ...]
    #: ``(name, uid)`` of every server the import registered.
    servers_added: tuple[tuple[str, str], ...]
    coffer_entry_results: tuple[ItemResult, ...]


class _Resources(Protocol):
    async def get(self, uid: str) -> Resource: ...

    async def update_scope(self, uid: str, scope: Scope | None, *, actor: str) -> Resource: ...


class _Applier(Protocol):
    async def apply(self, change_ids: Any, *, actor: str) -> Any: ...


def _error(e: Exception) -> tuple[str, str]:
    code = e.code if isinstance(e, CofferError) else "INTERNAL_ERROR"
    return code, str(e) if isinstance(e, CofferError) else type(e).__name__


class McpImportService:
    def __init__(
        self,
        *,
        planner: McpImportPlanner,
        entries: AgentMcpEntryService,
        resources: _Resources,
        reconciler: _Applier | None = None,
    ) -> None:
        self._planner = planner
        self._entries = entries
        self._rs = resources
        self._reconciler = reconciler

    async def plan(self, choices: Sequence[ImportChoice]) -> ImportPlan:
        return await self._planner.plan(choices)

    async def apply(self, choices: Sequence[ImportChoice], *, actor: str) -> ImportReport:
        plan = await self._planner.plan(choices)
        coffer = await self._apply_coffer_entries(plan, actor)
        outcomes: list[EntryOutcome] = [
            EntryOutcome(
                p.agent_uid, p.name, p.source, "skipped", None, None, p.error_code, p.error
            )
            for p in plan.unavailable
        ]
        added: list[tuple[str, str]] = []
        for server in plan.servers:
            if server.op == "add":
                resource = await self._add(server, outcomes, actor)
                if resource is not None:
                    added.append((resource.name, resource.uid))
                    await self._absorb(server, resource.uid, server.entries[1:], outcomes, actor)
            else:
                assert server.resource_uid is not None
                await self._absorb(server, server.resource_uid, server.entries, outcomes, actor)
        return ImportReport(tuple(outcomes), tuple(added), coffer)

    async def _apply_coffer_entries(self, plan: ImportPlan, actor: str) -> tuple[ItemResult, ...]:
        ids = [
            r.change.id
            for r in plan.coffer_entry_changes
            if r.change.decision.disposition is Disposition.REPAIR
        ]
        if not ids or self._reconciler is None:
            return ()
        report = await self._reconciler.apply(ids, actor=actor)
        return tuple(report.results)

    async def _add(
        self, server: PlannedServer, outcomes: list[EntryOutcome], actor: str
    ) -> Resource | None:
        source = server.entries[0]
        if not server.name_usable:
            for p in server.entries:
                outcomes.append(
                    self._failed(p, server.name, "NAME_UNUSABLE", self._bad_name(server))
                )
            return None
        try:
            resource = await self._entries.adopt(
                source.agent_uid,
                source.name,
                source=source.source,
                new_name=server.name if server.name != source.name else None,
                secrets=dict(source.secret_refs) or None,
                actor=actor,
            )
        except Exception as e:
            code, message = _error(e)
            for p in server.entries:
                outcomes.append(self._failed(p, server.name, code, message))
            return None
        try:
            resource = await self._rs.update_scope(
                resource.uid, Scope(agents=list(server.reach_agent_uids)), actor=actor
            )
        except Exception as e:
            # Registered and removed from the file: report the reach it kept.
            code, message = _error(e)
            outcomes.append(self._failed(source, resource.name, code, message, resource.uid))
            return resource
        outcomes.append(
            EntryOutcome(
                source.agent_uid, source.name, source.source, "added", resource.name, resource.uid
            )
        )
        return resource

    async def _absorb(
        self,
        server: PlannedServer,
        resource_uid: str,
        entries: Sequence[PlannedEntry],
        outcomes: list[EntryOutcome],
        actor: str,
    ) -> None:
        """Give each entry's agent the server through Coffer, then remove the entry."""
        outcome: Outcome = "merged" if server.op == "add" else "removed_duplicate"
        for p in entries:
            try:
                resource = await self._rs.get(resource_uid)
                scope = resource.scope
                if (
                    scope is not None
                    and scope.agents is not None
                    and p.agent_uid not in scope.agents
                ):
                    await self._rs.update_scope(
                        resource_uid, Scope(agents=[*scope.agents, p.agent_uid]), actor=actor
                    )
                await self._entries.remove_entry(p.agent_uid, p.name, source=p.source, actor=actor)
            except Exception as e:
                code, message = _error(e)
                outcomes.append(self._failed(p, server.name, code, message, resource_uid))
                continue
            outcomes.append(
                EntryOutcome(p.agent_uid, p.name, p.source, outcome, server.name, resource_uid)
            )

    @staticmethod
    def _bad_name(server: PlannedServer) -> str:
        return (
            f"{server.name!r} cannot be a server name (at most 24 characters: letters, "
            "digits, '.', '_' and '-'); give it another name."
        )

    @staticmethod
    def _failed(
        p: PlannedEntry, server: str, code: str, message: str, uid: str | None = None
    ) -> EntryOutcome:
        return EntryOutcome(p.agent_uid, p.name, p.source, "failed", server, uid, code, message)


__all__ = ["EntryOutcome", "ImportReport", "McpImportService"]
