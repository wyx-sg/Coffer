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


class MCPTool(BaseModel):
    name: str
    description: str | None = None
    input_schema: dict[str, Any]
    #: The MCP annotations the upstream declared (``readOnlyHint``,
    #: ``destructiveHint``, …), in their wire spelling; passed to the agent as
    #: they are (spec mcp-gateway "Annotate every tool with whether it changes data").
    annotations: dict[str, Any] | None = None
    #: The JSON Schema the upstream declared for the tool's ``structuredContent``
    #: (MCP ``outputSchema``), as declared; None when it declared none (spec
    #: mcp-gateway "Forward tools, resources and prompts").
    output_schema: dict[str, Any] | None = None


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
    """One capability's switch, with when this machine saw it. The switch is
    the person's (a vault document per server); the times are derived."""

    resource_uid: str
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
    #: label it happened to carry at the time (ADR identity-is-the-uid-inside-the-file).
    #: The log outlives a rename, so a name here would have split one server's
    #: history in two at the moment the user relabelled it — and joined two
    #: unrelated servers' histories together if a later registration reused the
    #: freed name. One reserved non-uid value exists, ``BUILTIN_SERVER_UID``,
    #: documented at the top of this module.
    resource_uid: str
    capability_type: CapabilityType
    capability_key: str
    duration_ms: int
    status: Literal["ok", "error", "timeout", "denied"]
    error_message: str | None = None
    session_id: str | None = None
    #: The agent whose session made the call, as the uid its shim reported on
    #: ``initialize``. ``None`` when the session reported none (a hand-configured
    #: shim, a bare MCP client): the log records what it was told, never a guess.
    agent_uid: str | None = None
    #: The ``/mcp`` request's trace id: the key that joins this
    #: call to the audit rows and daemon log lines it caused.
    trace_id: str | None = None
    #: The environment a custom-tool call was made in; ``None`` for every other
    #: call (spec mcp-gateway "Record invocations without content").
    environment: str | None = None
