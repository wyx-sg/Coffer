"""POST /api/v1/agents/mcp-import/{plan,apply} — import agents' direct MCP entries.

Spec agent-registry "Plan an import of agents' direct MCP entries" and "Apply an
import of agents' direct MCP entries". The Add server dialog's Import from your
agents shows the plan — servers added, merged or already in Coffer, and a
redacted per-file diff of each agent config file — before anything is written;
apply takes the same body and performs the plan recomputed at that moment.

No model here carries a secret value: diff lines are redacted (every
secret-looking key's value, and every secret value of any entry in the file,
context lines included), and an entry is described by its command, arguments,
URL and key names only. Secret refs are ref strings, never values.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from coffer.application.agent.mcp_import import ImportReport, McpImportService
from coffer.application.agent.mcp_import_types import (
    ImportChoice,
    ImportPlan,
    PlannedEntry,
    PlannedFile,
)
from coffer.domain.agent.config_diff import DiffHunk
from coffer.domain.reconcile import ItemResult as _ItemResult
from coffer.domain.reconcile import Outcome, PlannedChange
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor
from coffer.surfaces.http.reconcile_schemas import ReconcileItemOut, item_out

router = APIRouter(
    prefix="/api/v1/agents/mcp-import", tags=["agents"], dependencies=[Depends(require_token)]
)

_service: McpImportService | None = None


def set_mcp_import_service(svc: McpImportService | None) -> None:
    """Called by the composition root once on startup."""
    global _service
    _service = svc


def get_mcp_import_service() -> McpImportService:
    """FastAPI Depends() target."""
    if _service is None:
        raise RuntimeError("MCP import service not initialised")
    return _service


class McpImportEntryIn(BaseModel):
    agent_uid: str = Field(min_length=1)
    name: str = Field(min_length=1)
    #: The allowlisted config-file key the entry is in (``McpEntryOut.source``).
    source: str | None = None
    #: A name for the server this entry creates, instead of the normalised one.
    new_name: str | None = Field(default=None, max_length=64)


class McpImportIn(BaseModel):
    entries: list[McpImportEntryIn] = Field(min_length=1, max_length=200)


class McpImportPlanEntryOut(BaseModel):
    agent_uid: str
    agent_name: str
    name: str
    source: str | None
    path: str | None
    role: Literal["source", "merged", "duplicate", "unavailable"]
    transport: Literal["stdio", "http"] | None
    #: KEY NAMES whose values move into the keychain.
    secret_keys: list[str]
    #: KEY → the secret ref its value moves under (``mcp/<agent>/<entry>/<KEY>``).
    secret_refs: dict[str, str]
    error_code: str | None
    error: str | None


class McpImportServerOut(BaseModel):
    op: Literal["add", "duplicate"]
    name: str
    original_name: str | None
    name_usable: bool
    resource_uid: str | None
    transport: Literal["stdio", "http"]
    #: add: the agents it will reach. duplicate: the agents added to its reach.
    reach_agent_uids: list[str]
    #: duplicate: the server already reaches every agent.
    reaches_all: bool
    merged: bool = Field(description="Several entries become this one server.")
    settings_differ: bool = Field(
        description="Merged entries' environment or headers differ; the first entry's are kept."
    )
    entries: list[McpImportPlanEntryOut]


class DiffLineOut(BaseModel):
    kind: Literal["context", "add", "remove"]
    old_line: int | None
    new_line: int | None
    text: str


class DiffHunkOut(BaseModel):
    header: str = Field(description="`@@ -8,24 +8,5 @@ mcpServers`")
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    section: str | None
    lines: list[DiffLineOut]


class McpImportFileOut(BaseModel):
    agent_uid: str
    agent_type: str
    source: str
    op: Literal["modify"]
    path: str
    #: ``~/.claude.json``
    display_path: str
    entries_removed: list[str]
    added_lines: int
    removed_lines: int
    hunks: list[DiffHunkOut]


class McpImportAgentOut(BaseModel):
    uid: str
    name: str
    display_name: str
    type: str
    connected: bool = Field(description="Its config already holds Coffer's own entry.")
    entries_removed: list[str]


class McpImportPlanOut(BaseModel):
    """A dry run: nothing has been written."""

    servers: list[McpImportServerOut]
    files: list[McpImportFileOut]
    agents: list[McpImportAgentOut]
    unavailable: list[McpImportPlanEntryOut]
    #: The planned writes in the reconciler's vocabulary (target ``mcp_import``).
    changes: list[ReconcileItemOut]
    #: Differences the reconciler has pending on Coffer's own entry for these agents.
    coffer_entry_changes: list[ReconcileItemOut]


class McpImportEntryResultOut(BaseModel):
    agent_uid: str
    name: str
    source: str | None
    outcome: Literal["added", "merged", "removed_duplicate", "failed", "skipped"]
    server_name: str | None
    resource_uid: str | None
    error_code: str | None
    message: str | None


class McpImportServerAddedOut(BaseModel):
    name: str
    uid: str


class McpImportApplyOut(BaseModel):
    entries: list[McpImportEntryResultOut]
    servers_added: list[McpImportServerAddedOut]
    coffer_entry_results: list[ReconcileItemOut]


def _choices(body: McpImportIn) -> list[ImportChoice]:
    return [ImportChoice(e.agent_uid, e.name, e.source, e.new_name) for e in body.entries]


def _entry_out(p: PlannedEntry) -> McpImportPlanEntryOut:
    return McpImportPlanEntryOut(
        agent_uid=p.agent_uid,
        agent_name=p.agent_name,
        name=p.name,
        source=p.source,
        path=p.path,
        role=p.role,
        transport=p.transport,
        secret_keys=list(p.secret_keys),
        secret_refs=dict(p.secret_refs),
        error_code=p.error_code,
        error=p.error,
    )


def _hunk_out(h: DiffHunk) -> DiffHunkOut:
    return DiffHunkOut(
        header=h.header,
        old_start=h.old_start,
        old_count=h.old_count,
        new_start=h.new_start,
        new_count=h.new_count,
        section=h.section,
        lines=[DiffLineOut(kind=x.kind, old_line=x.old_line, new_line=x.new_line, text=x.text)
               for x in h.lines],
    )  # fmt: skip


def _file_out(f: PlannedFile) -> McpImportFileOut:
    return McpImportFileOut(
        agent_uid=f.agent_uid,
        agent_type=f.agent_type,
        source=f.source,
        op=f.op,
        path=f.path,
        display_path=f.display_path,
        entries_removed=list(f.entries_removed),
        added_lines=f.added_lines,
        removed_lines=f.removed_lines,
        hunks=[_hunk_out(h) for h in f.hunks],
    )


def _planned(change: PlannedChange) -> ReconcileItemOut:
    return item_out(_ItemResult(change, Outcome.PLANNED), None)


def plan_out(plan: ImportPlan) -> McpImportPlanOut:
    return McpImportPlanOut(
        servers=[
            McpImportServerOut(
                op=s.op,
                name=s.name,
                original_name=s.original_name,
                name_usable=s.name_usable,
                resource_uid=s.resource_uid,
                transport=s.transport,
                reach_agent_uids=list(s.reach_agent_uids),
                reaches_all=s.reaches_all,
                merged=s.op == "add" and len(s.entries) > 1,
                settings_differ=s.settings_differ,
                entries=[_entry_out(p) for p in s.entries],
            )
            for s in plan.servers
        ],
        files=[_file_out(f) for f in plan.files],
        agents=[
            McpImportAgentOut(
                uid=a.uid,
                name=a.name,
                display_name=a.display_name,
                type=a.agent_type,
                connected=a.connected,
                entries_removed=list(a.entries_removed),
            )
            for a in plan.agents
        ],
        unavailable=[_entry_out(p) for p in plan.unavailable],
        changes=[_planned(c) for c in plan.changes],
        coffer_entry_changes=[item_out(r, None) for r in plan.coffer_entry_changes],
    )


def report_out(report: ImportReport) -> McpImportApplyOut:
    return McpImportApplyOut(
        entries=[
            McpImportEntryResultOut(
                agent_uid=e.agent_uid,
                name=e.name,
                source=e.source,
                outcome=e.outcome,
                server_name=e.server_name,
                resource_uid=e.resource_uid,
                error_code=e.error_code,
                message=e.message,
            )
            for e in report.entries
        ],
        servers_added=[McpImportServerAddedOut(name=n, uid=u) for n, u in report.servers_added],
        coffer_entry_results=[item_out(r, None) for r in report.coffer_entry_results],
    )


@router.post("/plan", response_model=McpImportPlanOut)
async def plan_import(
    body: McpImportIn,
    svc: McpImportService = Depends(get_mcp_import_service),  # noqa: B008
) -> McpImportPlanOut:
    """What importing the chosen entries would do; writes nothing."""
    return plan_out(await svc.plan(_choices(body)))


@router.post("/apply", response_model=McpImportApplyOut)
async def apply_import(
    body: McpImportIn,
    actor: str = Depends(get_actor),
    svc: McpImportService = Depends(get_mcp_import_service),  # noqa: B008
) -> McpImportApplyOut:
    """Perform the plan as it stands now; each entry reports its outcome."""
    return report_out(await svc.apply(_choices(body), actor=actor))
