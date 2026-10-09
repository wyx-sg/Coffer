"""Wire shapes of the two growing logs: the audit log and the MCP invocation log.

Both page by an opaque cursor (spec resource-framework "Page growing lists by
an opaque cursor"): each answer carries ``next_cursor``, null on the last page.
Split out of ``schemas.py`` for the file-size budget.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from coffer.surfaces.http.handoff_schemas import HandoffOut

# --- Audit ---


class AuditEntryOut(BaseModel):
    id: int
    timestamp: datetime
    event_type: str
    resource_kind: str | None = None
    #: The label the resource carried WHEN THE EVENT HAPPENED, which is the
    #: point of storing it: a renamed resource's history reads as the history
    #: of a thing that was called different names at different times.
    resource_name: str | None = None
    actor: str
    details: dict[str, Any] | None = None
    #: The request's or turn's correlation id; the same value the MCP
    #: invocations and daemon log lines of that request or turn carry. Null on a
    #: row written with none bound (a boot-time pass, a periodic worker).
    trace_id: str | None = None
    #: The chat conversation and turn a row written inside a turn belongs to.
    conversation_id: str | None = None
    turn_id: str | None = None


class AuditListOut(BaseModel):
    """One page of the audit log, newest first."""

    entries: list[AuditEntryOut]
    #: Continues the list after ``entries``; null exactly on the last page.
    next_cursor: str | None
    total: int = Field(
        description=(
            "How many rows match the filters, across every page; the cursor does not change it."
        )
    )


# --- MCP invocations ---


class InvocationOut(BaseModel):
    #: The row's id in the log — stable, unique, and the tie-break of its order.
    id: int
    timestamp: datetime
    #: Which upstream server the call went to — the value actually recorded in
    #: the log, and what to filter or link by. Required, not optional: the
    #: cross-server timeline is unreadable without it, and the per-server route
    #: knows it too. It is a resource uid, except for ``BUILTIN_SERVER_UID``
    #: ("coffer"), the sentinel Coffer's own built-in tools log under; a uid
    #: whose server has since been deleted resolves to nothing as well.
    resource_uid: str
    #: The same server's label, resolved at read time by the route, so the
    #: timeline is readable without a client holding the whole resource list.
    #: Null when ``resource_uid`` resolves to no resource — a deleted server, or
    #: the built-in sentinel — which is where a client falls back to showing the
    #: uid's own text. Nullable but NOT defaulted: a projection that forgot to
    #: resolve would otherwise silently emit null for every row.
    resource_name: str | None
    #: ``domain.mcp.capability.CapabilityType``, spelled out: this module is
    #: kind-agnostic core and may not import the mcp kind.
    capability_type: Literal["tool", "resource", "prompt"]
    capability_key: str
    duration_ms: int
    status: Literal["ok", "error", "timeout", "denied"]
    error_message: str | None = None
    session_id: str | None = None
    #: The ``/mcp`` request's trace id, the key that joins this call to the
    #: audit rows and daemon log lines it caused. Null on rows logged before
    #: correlation ids existed.
    trace_id: str | None = None
    #: The agent whose session made the call — the uid its shim reported — or
    #: null when the session reported none. Nullable but NOT defaulted, like
    #: ``resource_name``: the projection sets it on every row.
    agent_uid: str | None
    #: The environment a custom-tool call was made in; null for any other call.
    environment: str | None = None
    #: For a call its server never answered (refused, timed out, would not
    #: start): the chore of finding out why, for the person's agent. Null for
    #: every other call — a success, a denial, or an upstream that answered
    #: with its own error.
    handoff: HandoffOut | None = None


class CapturedPartOut(BaseModel):
    """One recorded part of a call: its JSON (or the first 16 KB of it), redacted."""

    text: str
    #: Cut at 16 KB; ``text`` is then a prefix and may not parse.
    truncated: bool
    #: The part's size, in UTF-8 bytes, before any cut.
    bytes: int


class InvocationContentOut(BaseModel):
    """What a call carried (spec mcp-gateway "Record invocations with redacted,
    bounded content"). A part the call did not have is null."""

    arguments: CapturedPartOut | None = None
    result: CapturedPartOut | None = None
    error: CapturedPartOut | None = None
    #: A custom tool's request (method, url, headers, body) and response
    #: (status, headers, body); null for any other call.
    request: CapturedPartOut | None = None
    response: CapturedPartOut | None = None


class InvocationDetailOut(InvocationOut):
    """One call, with its content; ``content`` is null for a call recorded
    while recording was off."""

    content: InvocationContentOut | None


class CallContentSettingOut(BaseModel):
    """Whether calls record their arguments and results on this machine."""

    enabled: bool


class CallContentSettingIn(BaseModel):
    enabled: bool


class InvocationListOut(BaseModel):
    """One page of the invocation log, newest first."""

    invocations: list[InvocationOut]
    #: Continues the list after ``invocations``; null exactly on the last page.
    next_cursor: str | None
    total: int = Field(
        description=(
            "How many rows match the filters, across every page; the cursor does not change it."
        )
    )
