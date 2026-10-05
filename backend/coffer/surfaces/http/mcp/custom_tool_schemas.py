"""Wire models of the custom tools routes (spec mcp-gateway "Manage custom
tools through REST and the Custom tools page"; design add-http-custom-tools §9).

These are the only hand-written description of the wire: the contract in
``openspec/specs/mcp-gateway/contracts/api.openapi.yaml`` and the frontend's
types are generated from them. A group's secret travels by its Secrets-page
name, never as a ref or a value.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from coffer.domain.auth_scheme import AuthScheme
from coffer.surfaces.http.handoff_schemas import HandoffOut

HttpMethodName = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
GroupHealthName = Literal["failing", "attention", "healthy", "idle", "off"]
SecretStateName = Literal["none", "present", "missing", "pending_approval"]
#: How a test run failed before the API answered: the request could not be
#: built, it timed out, it could not connect, or the address was refused.
TestFailureName = Literal["request", "timeout", "connect", "blocked"]


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
    #: The operation's spec text, kept from an import for the re-import diff.
    source_text: str | None = None


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
    calls_24h: int
    failures_24h: int


class CustomToolHeaderIn(BaseModel):
    """One group header row: a plain value, or a stored secret holding the
    credential alone. Send one of the two."""

    name: str
    value: str | None = None
    #: The secret's name on the Secrets page.
    secret: str | None = None
    #: A secret row's scheme, sent in front of the secret (``Bearer <key>``);
    #: ``null`` sends the secret as it is.
    scheme: AuthScheme | None = None


class CustomToolHeaderOut(BaseModel):
    name: str
    #: The plain value; ``null`` when the value is a secret.
    value: str | None
    secret: str | None
    #: A secret row's scheme; ``null`` for a plain row or a secret sent as is.
    scheme: AuthScheme | None = None
    #: ``none`` for a plain row.
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
    headers: list[CustomToolHeaderIn] = Field(default_factory=list)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    #: The group's reach: agent uids (at least one), or ``null`` for every agent.
    agents: list[str] | None = None
    tools: list[CustomToolIn] = Field(default_factory=list)
    source: OpenApiSourceIn | None = None


class CustomToolGroupPatch(BaseModel):
    """A partial change to a group; ``headers`` replaces the whole list."""

    description: str | None = None
    base_url: str | None = None
    headers: list[CustomToolHeaderIn] | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=300)


class CustomToolGroupOut(BaseModel):
    uid: str
    name: str
    description: str | None
    enabled: bool
    base_url: str
    headers: list[CustomToolHeaderOut]
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
    #: The names of the secrets whose approval is pending, for "<secret> waits
    #: for approval".
    pending_secrets: list[str]
    calls_24h: int
    failures_24h: int
    last_call_at: datetime | None
    #: A failing group (its last call failed): the prompt that hands finding why to
    #: an agent. ``null`` otherwise.
    handoff: HandoffOut | None = None
    tools: list[CustomToolOut]
    created_at: datetime
    updated_at: datetime


class CustomToolGroupListOut(BaseModel):
    groups: list[CustomToolGroupOut]


class CustomToolTestIn(BaseModel):
    tool: CustomToolIn
    arguments: dict[str, Any] = Field(default_factory=dict)


class CustomToolUnsavedTestIn(BaseModel):
    """A request tested before its group exists: the group's settings inline.

    No secret travels: an unsaved group has no approved binding, so a secret
    header row is left out of the test.
    """

    base_url: str
    headers: list[CustomToolHeaderIn] = Field(default_factory=list)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
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
    #: Set when no answer came back; ``null`` when the API answered.
    failure: TestFailureName | None = None
    #: A test that could not connect or timed out: the prompt that hands the
    #: network problem to an agent. ``null`` for anything else.
    handoff: HandoffOut | None = None


class OpenApiReadIn(BaseModel):
    """A document to read: its URL (fetched through the SSRF guard) or its text."""

    url: str | None = None
    document: str | None = Field(default=None, max_length=5 * 1024 * 1024)
    filename: str | None = None


class OpenApiSourceTextOut(BaseModel):
    """An operation's text in the document, for the viewer beside the list."""

    #: 1-based, inclusive line numbers in the document.
    start_line: int
    end_line: int
    text: str


class OpenApiOperationOut(BaseModel):
    key: str
    summary: str | None
    #: The operation's first tag, for grouping in the import form.
    tag: str | None = None
    tool: CustomToolIn
    #: ``null`` when the operation could not be located in the document.
    source: OpenApiSourceTextOut | None = None


class OpenApiReadOut(BaseModel):
    title: str | None
    version: str | None
    #: The spec's ``info.description``; the form pre-fills the group's description.
    description: str | None = None
    base_url: str | None
    #: The header the spec's security scheme puts a credential in (``Authorization``
    #: for bearer, basic and OAuth; the key's name for an API key); the form
    #: pre-fills one such header row with no value.
    auth_header: str | None
    source_kind: Literal["url", "file"]
    location: str
    operations: list[OpenApiOperationOut]
    warnings: list[str]


class CustomToolReimportIn(BaseModel):
    #: The document again, for a group imported from a file.
    document: str | None = Field(default=None, max_length=5 * 1024 * 1024)
    #: Keys of the added operations to import (switched on); the rest are skipped.
    add: list[str] = Field(default_factory=list)


class CustomToolReimportChangeOut(BaseModel):
    """A kept tool whose request the spec changed."""

    name: str
    method: HttpMethodName
    path: str
    #: Arguments the spec now requires that the tool did not.
    new_required: list[str]
    #: The method, path or body template moved.
    request_changed: bool
    #: ``"<METHOD> <path>"`` of the operation.
    operation: str
    #: The operation's spec text as last imported; ``null`` for a tool imported
    #: before Coffer kept it. The change preview diffs this against ``new_text``.
    old_text: str | None = None
    new_text: str | None = None
    new_start_line: int | None = None
    new_end_line: int | None = None


class CustomToolReimportPreviewOut(BaseModel):
    title: str | None
    version: str | None
    added: list[OpenApiOperationOut]
    removed: list[str]
    kept: list[str]
    #: Kept tools the spec changed (a subset of ``kept``).
    changed: list[CustomToolReimportChangeOut] = Field(default_factory=list)
    warnings: list[str]
