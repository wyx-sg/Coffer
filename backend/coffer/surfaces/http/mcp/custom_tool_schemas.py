"""Wire models of the custom tools routes (spec mcp-gateway "Manage custom tools
on REST and the command line"; design add-http-custom-tools §9).

These are the only hand-written description of the wire: the contract in
``openspec/specs/mcp-gateway/contracts/api.openapi.yaml`` and the frontend's
types are generated from them. A group's secret travels by its Secrets-page
name, never as a ref or a value.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

HttpMethodName = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
GroupHealthName = Literal["failing", "attention", "healthy", "idle", "off"]
SecretStateName = Literal["none", "present", "missing", "pending_approval"]


def _empty_schema() -> dict[str, Any]:
    return {"type": "object", "properties": {}}


class CustomToolIn(BaseModel):
    """One tool as a request writes it — and as an OpenAPI reading drafts it."""

    name: str
    description: str = ""
    method: HttpMethodName = "GET"
    path: str
    headers: dict[str, str] = Field(default_factory=dict)
    body_template: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=_empty_schema)
    enabled: bool = True
    #: ``null`` follows the method: on for every method but GET.
    changes_data: bool | None = None
    operation: str | None = None


class CustomToolPatch(BaseModel):
    """A partial change to one tool: only the fields sent change."""

    name: str | None = None
    description: str | None = None
    method: HttpMethodName | None = None
    path: str | None = None
    headers: dict[str, str] | None = None
    body_template: str | None = None
    input_schema: dict[str, Any] | None = None
    enabled: bool | None = None
    changes_data: bool | None = None


class CustomToolOut(BaseModel):
    name: str
    #: What an agent sees: ``<group>__<tool>``.
    agent_name: str
    description: str
    method: HttpMethodName
    path: str
    headers: dict[str, str]
    body_template: str | None
    input_schema: dict[str, Any]
    enabled: bool
    #: The flag in force (the method's default when none was set).
    changes_data: bool
    #: Whether the flag was set by hand rather than following the method.
    changes_data_set: bool
    operation: str | None
    #: Agent uids the tool is narrowed to; ``null`` follows the group.
    reach_override: list[str] | None
    calls_24h: int
    failures_24h: int


class CustomToolAuthIn(BaseModel):
    header: str = "Authorization"
    prefix: str = ""
    #: The secret's name on the Secrets page; ``null`` leaves the header unbound.
    secret: str | None = None


class CustomToolAuthOut(BaseModel):
    header: str
    prefix: str
    secret: str | None
    secret_state: SecretStateName


class OpenApiSourceIn(BaseModel):
    kind: Literal["url", "file"]
    location: str
    title: str | None = None
    version: str | None = None
    #: Operation keys (``"<METHOD> <path>"``) read and not imported.
    skipped: list[str] = Field(default_factory=list)


class OpenApiSourceOut(BaseModel):
    kind: Literal["url", "file"]
    location: str
    title: str | None
    version: str | None
    fetched_at: datetime
    skipped: list[str]


class CustomToolGroupIn(BaseModel):
    name: str
    description: str | None = None
    base_url: str
    headers: dict[str, str] = Field(default_factory=dict)
    auth: CustomToolAuthIn | None = None
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    #: The group's reach: agent uids, or ``null`` for every agent.
    agents: list[str] | None = None
    tools: list[CustomToolIn] = Field(default_factory=list)
    source: OpenApiSourceIn | None = None


class CustomToolGroupPatch(BaseModel):
    """A partial change to a group; ``auth: null`` removes the auth header."""

    description: str | None = None
    base_url: str | None = None
    headers: dict[str, str] | None = None
    auth: CustomToolAuthIn | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=300)


class CustomToolGroupOut(BaseModel):
    uid: str
    name: str
    description: str | None
    enabled: bool
    base_url: str
    headers: dict[str, str]
    auth: CustomToolAuthOut | None
    timeout_seconds: int
    #: The group's reach as agent uids; ``null`` is every agent.
    scope: list[str] | None
    source: OpenApiSourceOut | None
    health: GroupHealthName
    #: ``last_call_failed``, ``secret_missing`` or ``approval_pending``.
    health_reason: str | None
    secret_state: SecretStateName
    #: The secret approvals this group waits on.
    pending_approvals: list[str]
    calls_24h: int
    failures_24h: int
    last_call_at: datetime | None
    tools: list[CustomToolOut]
    created_at: datetime
    updated_at: datetime


class CustomToolGroupListOut(BaseModel):
    groups: list[CustomToolGroupOut]


class CustomToolReachIn(BaseModel):
    #: Agent uids the tool is narrowed to; ``null`` clears the override.
    agents: list[str] | None = None


class CustomToolTestIn(BaseModel):
    tool: CustomToolIn
    arguments: dict[str, Any] = Field(default_factory=dict)


class CustomToolTestOut(BaseModel):
    ok: bool
    duration_ms: int
    url: str | None
    status: int | None
    status_line: str | None
    body: str
    truncated: bool
    content_type: str | None
    error: str | None


class OpenApiReadIn(BaseModel):
    """A document to read: its URL (fetched through the SSRF guard) or its text."""

    url: str | None = None
    document: str | None = Field(default=None, max_length=5 * 1024 * 1024)
    filename: str | None = None


class OpenApiOperationOut(BaseModel):
    key: str
    summary: str | None
    tool: CustomToolIn


class OpenApiReadOut(BaseModel):
    title: str | None
    version: str | None
    base_url: str | None
    auth_header: str | None
    auth_prefix: str
    source_kind: Literal["url", "file"]
    location: str
    operations: list[OpenApiOperationOut]
    warnings: list[str]


class CustomToolReimportIn(BaseModel):
    #: The document again, for a group imported from a file.
    document: str | None = Field(default=None, max_length=5 * 1024 * 1024)
    #: Keys of the added operations to import (switched on); the rest are skipped.
    add: list[str] = Field(default_factory=list)


class CustomToolReimportPreviewOut(BaseModel):
    title: str | None
    version: str | None
    added: list[OpenApiOperationOut]
    removed: list[str]
    kept: list[str]
    warnings: list[str]
