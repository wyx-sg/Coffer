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
    resource_name: str
    capability_type: CapabilityType
    capability_key: str
    duration_ms: int
    status: Literal["ok", "error", "timeout", "denied"]
    error_message: str | None = None
    session_id: str | None = None
