"""MCP capability value objects.

Live (non-persisted) shapes for tools / resources / prompts as returned
by upstream `list_*` queries, plus persisted entities for capability
preferences and invocation records.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

CapabilityType = Literal["tool", "resource", "prompt"]

#: The value :class:`MCPInvocation.resource_uid` carries for one of Coffer's own
#: ``coffer__*`` built-in tools. Built-ins share the invocation log with upstream
#: servers so retention and the activity surfaces work uniformly, but there is no
#: ``mcp_server`` row behind them and therefore no uid to record. A real uid is a
#: 32-character ``uuid4().hex``, so this literal can never collide with one.
BUILTIN_SERVER_UID = "coffer"

#: The prefix migration 0091 gave an invocation whose server had already been
#: deleted when the log was re-keyed from names to uids. The identity of such a
#: row was never recorded and cannot be recovered, so the label it *did* carry is
#: preserved behind a marker that is visibly not a uid — the history survives, the
#: row joins to no resource, and nothing mistakes the leftover for an identity.
DELETED_SERVER_UID_PREFIX = "deleted:"


class MCPTool(BaseModel):
    name: str
    description: str | None = None
    input_schema: dict[str, Any]


class MCPResource(BaseModel):
    uri: str
    name: str | None = None
    description: str | None = None
    mime_type: str | None = None


class MCPPromptArgument(BaseModel):
    name: str
    description: str | None = None
    required: bool = False


class MCPPrompt(BaseModel):
    name: str
    description: str | None = None
    arguments: list[MCPPromptArgument] = []


@dataclass
class MCPCapabilityPreference:
    """One row in mcp_capability_preferences. ID is None until persisted."""

    id: int | None
    resource_id: int
    capability_type: CapabilityType
    capability_key: str
    enabled: bool
    first_seen_at: datetime
    last_seen_at: datetime


@dataclass
class MCPInvocation:
    """One row in mcp_invocations. NEVER carries args or result content."""

    id: int | None
    timestamp: datetime
    #: WHICH server was invoked, by its immutable identity rather than by the
    #: label it happened to carry at the time (ADR resource-identity-is-an-immutable-uid).
    #: The log outlives a rename, so a name here would have split one server's
    #: history in two at the moment the user relabelled it — and joined two
    #: unrelated servers' histories together if a later registration reused the
    #: freed name. Two reserved non-uid values exist and are documented at the
    #: top of this module: ``BUILTIN_SERVER_UID`` and the
    #: ``DELETED_SERVER_UID_PREFIX`` form.
    resource_uid: str
    capability_type: CapabilityType
    capability_key: str
    duration_ms: int
    status: Literal["ok", "error", "timeout", "denied"]
    error_message: str | None = None
    session_id: str | None = None
