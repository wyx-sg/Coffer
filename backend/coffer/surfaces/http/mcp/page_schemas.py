"""Wire models of the MCP server page's reads (status, 24 h summary, server log, tiering)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from coffer.infrastructure.mcp.invocation_summary import InvocationSummary
from coffer.surfaces.http.handoff_schemas import HandoffOut


class McpServerStatusOut(BaseModel):
    """Cheap per-server status, derived from persisted state (no spawn).

    Beside the state word, what the page says about it (spec mcp-gateway
    "Explain a server's state on its page"): the last transport failure and
    since when the server has been failing, the last successful call, and the
    first cited secret with no value on this machine. Each is null when
    nothing persisted says it.
    """

    status: Literal["healthy", "failing", "unknown"]
    # A stdio server whose launcher command does not resolve on THIS machine
    # (a synced server referencing e.g. uvx on a machine without uv). The UI
    # renders "missing <runner>" so the cause is visible.
    missing_runner: str | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None
    failing_since: datetime | None = None
    #: When the health record (a test) was last written.
    last_checked_at: datetime | None = None
    last_ok_at: datetime | None = None
    #: The capability the last successful call reached (a tool name, a URI).
    last_ok_capability: str | None = None
    #: The environment or header key citing a secret this machine does not hold…
    missing_secret: str | None = None
    #: …and the secret's own reference, which is what the user recognises.
    missing_secret_ref: str | None = None
    #: The chore for the person's agent when the server needs one: installing
    #: its missing launcher, or finding why it fails (spec mcp-gateway "Name a
    #: missing stdio launcher", "Hand a failing MCP server's diagnosis to an
    #: agent"). Null for a server that is healthy, unknown or missing a secret.
    handoff: HandoffOut | None = None


class CallCountOut(BaseModel):
    calls: int
    errors: int
    last_call_at: datetime | None = None


class AgentCallCountOut(CallCountOut):
    #: The calling agent's uid; null for sessions that reported none.
    agent_uid: str | None = None


class ToolCallCountOut(CallCountOut):
    #: The upstream's own tool name (the capability list's ``original_name``).
    tool: str


class InvocationSummaryOut(BaseModel):
    """One server's calls since ``since``: totals, per agent, per tool."""

    since: datetime
    calls: int
    #: Calls that did not end ``ok``.
    errors: int
    last_call_at: datetime | None = None
    by_agent: list[AgentCallCountOut] = Field(default_factory=list)
    by_tool: list[ToolCallCountOut] = Field(default_factory=list)


def invocation_summary_out(summary: InvocationSummary) -> InvocationSummaryOut:
    """The persisted summary as the page reads it."""
    return InvocationSummaryOut(
        since=summary.since,
        calls=summary.calls,
        errors=summary.errors,
        last_call_at=summary.last_call_at,
        by_agent=[
            AgentCallCountOut(
                agent_uid=c.key, calls=c.calls, errors=c.errors, last_call_at=c.last_call_at
            )
            for c in summary.by_agent
        ],
        by_tool=[
            ToolCallCountOut(
                tool=c.key or "", calls=c.calls, errors=c.errors, last_call_at=c.last_call_at
            )
            for c in summary.by_tool
        ],
    )


class McpServerLogLineOut(BaseModel):
    text: str
    #: ``coffer`` for a line Coffer wrote about starting or stopping the
    #: server, ``stderr`` for what the server printed.
    source: Literal["coffer", "stderr"]
    at: datetime | None = None


class McpServerLogOut(BaseModel):
    """The newest lines of the server's own log file, newest first."""

    #: The file read; null when there is none (an HTTP server, or a stdio
    #: server Coffer has not started yet).
    path: str | None = None
    lines: list[McpServerLogLineOut] = Field(default_factory=list)
    #: More, older lines exist than were returned.
    truncated: bool = False


class ToolExposureOut(BaseModel):
    """One tool's exposure: what the person set, what agents get, and why."""

    tool: str
    #: The person's setting: ``auto`` (usage decides), ``listed`` (pinned) or ``search``.
    mode: Literal["auto", "listed", "search"]
    #: What agents get now: listed in ``tools/list`` or reached through search.
    effective: Literal["listed", "search"]
    reason: Literal["pinned", "search_only", "within_budget", "top_by_use", "low_use"]


class ToolExposureBody(BaseModel):
    mode: Literal["auto", "listed", "search"]


class ToolExposureBatchBody(BaseModel):
    tools: list[str] = Field(min_length=1)
    mode: Literal["auto", "listed", "search"]


class ToolTieringOut(BaseModel):
    """Which of this server's tools agents see listed and which only through search.

    Machine-wide: computed over every enabled server's saved tool list, not
    per agent reach (spec mcp-gateway "Forward tools, resources and prompts").
    """

    enabled: bool
    budget: int
    #: Upstream tools across every enabled server on this machine.
    catalogue_size: int
    #: Of those, how many are listed directly.
    listed_count: int
    #: This server's current tools, on or off.
    tool_count: int
    listed: list[str] = Field(default_factory=list)
    behind_search: list[str] = Field(default_factory=list)
    #: This server's enabled tools with their exposure and the reason for it.
    tools: list[ToolExposureOut] = Field(default_factory=list)
