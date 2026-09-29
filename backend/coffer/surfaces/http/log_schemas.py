"""Wire shapes of the two growing logs: the audit log and the MCP invocation log.

Both page by an opaque cursor (spec resource-framework "Page growing lists by
an opaque cursor"): each answer carries ``next_cursor``, null on the last page.
Split out of ``schemas.py`` for the file-size budget.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

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


class AuditListOut(BaseModel):
    """One page of the audit log, newest first."""

    entries: list[AuditEntryOut]
    #: Continues the list after ``entries``; null exactly on the last page.
    next_cursor: str | None


# --- MCP invocations ---


class InvocationOut(BaseModel):
    timestamp: datetime
    #: Which upstream server the call went to — the value actually recorded in
    #: the log, and what to filter or link by. Required, not optional: the
    #: cross-server timeline is unreadable without it, and the per-server route
    #: knows it too. Two of its forms are not resource uids and resolve to
    #: nothing: ``BUILTIN_SERVER_UID`` ("coffer"), the sentinel Coffer's own
    #: built-in tools log under, and the ``DELETED_SERVER_UID_PREFIX`` form
    #: ("deleted:<name>") given to rows whose server was already gone when the
    #: log was re-keyed from names to uids.
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


class InvocationListOut(BaseModel):
    """One page of the invocation log, newest first."""

    invocations: list[InvocationOut]
    #: Continues the list after ``invocations``; null exactly on the last page.
    next_cursor: str | None
