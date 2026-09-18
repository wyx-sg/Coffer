"""Pydantic API schemas (kind-agnostic).

Wire-compatible with specs/mcp-gateway/contracts/api.openapi.yaml.
MCP-kind-specific schemas live in surfaces/http/mcp/schemas.py (Phase 3).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from coffer.domain.scope import Scope

# --- Error envelope ---


class ErrorDetail(BaseModel):
    code: str = Field(examples=["RESOURCE_NOT_FOUND"])
    message: str = Field(examples=["resource not found: mcp_server:filesystem"])
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail


# --- Resources (kind-agnostic) ---


class ScopeOut(BaseModel):
    """A resource's activation scope on the wire: one allow-list of agents
    (ADR per-agent-resource-scope). ``null`` means unrestricted; ``[]`` matches
    nothing, i.e. dormant.

    Extra keys are REFUSED rather than ignored, which is the unusual choice and
    the deliberate one. This model used to carry a second axis, ``machines``,
    and a client that still sends it — a browser tab left open across the
    upgrade — means "only on that machine". Ignoring the key would store what
    is left, ``agents: null``, and that reads as *every agent, everywhere*: the
    request would silently widen the very restriction it was trying to write.
    A 422 tells the caller its request was not understood, which is the only
    honest answer.
    """

    model_config = ConfigDict(extra="forbid")

    agents: list[str] | None = Field(default=None, examples=[["claude-code"]])

    @classmethod
    def of(cls, scope: Scope | None) -> ScopeOut | None:
        """The wire shape of a stored scope; null stays null (unscoped)."""
        return None if scope is None else cls(agents=scope.agents)

    def to_domain(self) -> Scope:
        return Scope(agents=self.agents)


class ResourceOut(BaseModel):
    ref: str = Field(examples=["mcp_server:filesystem"])
    kind: str
    name: str
    description: str | None = None
    config: dict[str, Any]
    # Framework-level activation scope (ADR per-agent-resource-scope). None =
    # unscoped (active for every agent); only kinds whose Kind.supports_scope
    # is True may set it. See GET/PUT .../scope below.
    scope: ScopeOut | None = None
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ResourceCreate(BaseModel):
    kind: str
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_.\-]+$")
    description: str | None = None
    config: dict[str, Any]


class ResourceUpdate(BaseModel):
    #: A new name for this resource. Absent leaves it alone; present on a kind
    #: that does not support renaming is a 409, not a silent no-op. The URL
    #: still names the resource being edited, so this is the new label rather
    #: than a second way to address it.
    name: str | None = Field(
        default=None, min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_.\-]+$"
    )
    description: str | None = None
    config: dict[str, Any] | None = None


class ResourceListOut(BaseModel):
    resources: list[ResourceOut]


class ResourceScopeOut(BaseModel):
    """GET .../scope response: the current scope plus whether this kind
    supports scope at all (False means any non-null write is a 422)."""

    scope: ScopeOut | None = None
    supports_scope: bool = False


class ResourceScopeUpdate(BaseModel):
    """PUT .../scope request body: which agents this resource is active for.

    ``scope: null`` clears back to unscoped — every agent. A list restricts to
    exactly those agents, and an empty list matches nothing, so
    ``{"agents": []}`` is dormant.

    Scope is set per machine and does not sync: every machine holding this
    vault decides for itself which of its agents a resource activates for."""

    scope: ScopeOut | None = None


# --- Audit ---


class AuditEntryOut(BaseModel):
    id: int
    timestamp: datetime
    event_type: str
    resource_kind: str | None = None
    resource_name: str | None = None
    actor: str
    details: dict[str, Any] | None = None


class AuditListOut(BaseModel):
    entries: list[AuditEntryOut]


# --- Retention ---


class RetentionPolicyOut(BaseModel):
    table_name: str
    display_name: str
    description: str
    default_retention_days: int | None
    retention_days: int | None
    last_pruned_at: datetime | None = None
    last_pruned_rows: int


class RetentionPolicyListOut(BaseModel):
    policies: list[RetentionPolicyOut]


class RetentionPolicyUpdate(BaseModel):
    retention_days: int | None = Field(
        default=None,
        ge=1,
        le=3650,
        description="Null = keep forever; 1..3650 days otherwise.",
    )


class PruneResultOut(BaseModel):
    tables: dict[str, int]


# --- Daemon ---


class UpstreamSummary(BaseModel):
    registered: int
    enabled: int
    healthy: int
    unhealthy: int


class DaemonStatusOut(BaseModel):
    status: Literal["starting", "ready", "draining"]
    version: str
    #: The daemon process's ``sys.executable`` — the frozen binary or the
    #: interpreter — so a caller reporting version skew can name the build.
    executable: str
    started_at: datetime
    port: int
    upstream_summary: UpstreamSummary | None = None


class TokenRotationOut(BaseModel):
    token: str = Field(description="New token; clients must re-read daemon.json")


class DaemonLogRecordOut(BaseModel):
    """One record of ``daemon.log``, parsed where possible.

    ``daemon.log`` interleaves several writers — Coffer's structlog JSON, the
    stdlib formatter, uvicorn, rich, and the cloudflared child's zerolog — so
    ``record`` carries whatever that line stated, normalised onto ``timestamp``
    / ``level`` / ``logger`` / ``event``, plus ``continuation`` for the lines
    (a traceback, a wrapped message) that belong to this record rather than to
    one of their own. A line no writer's format fits is kept whole as
    ``{"raw": <line>}``. The three lifted fields are what a timeline renders
    without knowing any of that; they are absent on a raw line, which is why
    they are nullable.
    """

    timestamp: str | None = None
    level: str | None = None
    #: The message — structlog's ``event`` field, or the text another writer
    #: put after its level.
    event: str | None = None
    record: dict[str, Any]


class DaemonLogListOut(BaseModel):
    records: list[DaemonLogRecordOut]


# --- MCP capability views ---


class MCPToolView(BaseModel):
    prefixed_name: str = Field(examples=["filesystem__read_file"])
    original_name: str = Field(examples=["read_file"])
    description: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
    enabled: bool


class MCPResourceView(BaseModel):
    prefixed_uri: str
    original_uri: str
    name: str | None = None
    description: str | None = None
    mime_type: str | None = None
    enabled: bool


class _MCPPromptArgument(BaseModel):
    name: str
    description: str | None = None
    required: bool = False


class MCPPromptView(BaseModel):
    prefixed_name: str
    original_name: str
    description: str | None = None
    arguments: list[_MCPPromptArgument] = Field(default_factory=list)
    enabled: bool


class CapabilityListOut(BaseModel):
    server_name: str
    tools: list[MCPToolView]
    resources: list[MCPResourceView]
    prompts: list[MCPPromptView]
    fetched_at: datetime
    from_cache: bool = False


class McpTestResultOut(BaseModel):
    ok: bool
    latency_ms: int
    protocol_version: str | None = None
    server_capabilities: dict[str, Any] | None = None
    error_message: str | None = None


class InvocationOut(BaseModel):
    timestamp: datetime
    #: Which upstream server the call went to. Required, not optional: the
    #: cross-server timeline is unreadable without it, and the per-server
    #: route knows it too.
    resource_name: str
    capability_type: str = Field(pattern="^(tool|resource|prompt)$")
    capability_key: str
    duration_ms: int
    status: str
    error_message: str | None = None
    session_id: str | None = None


class InvocationListOut(BaseModel):
    invocations: list[InvocationOut]


# --- Credentials ---


class CredentialSetIn(BaseModel):
    """Request body for storing a secret in the credential store.

    Secrets are Fernet-encrypted into the coffer DB; only ciphertext is
    persisted; audit rows carry the ref only.
    """

    ref: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$",
        description=(
            "Reference key the secret is stored under. Slash-separated "
            "segments are allowed (e.g. channel/tg/bot-token)."
        ),
    )
    value: str = Field(
        min_length=1,
        max_length=8192,
        description="The secret value.",
    )


class CredentialExistsOut(BaseModel):
    """Presence-only response — never carries the secret value."""

    present: bool = Field(description="Whether a secret is stored under the ref.")


class CredentialGetOut(BaseModel):
    """Secret-value response for an explicit read from the credential store."""

    value: str = Field(description="The stored secret value.")


# --- MCP capability enable/disable body ---


class CapabilityKeyBody(BaseModel):
    """Request body for capability enable/disable routes.

    Carries the capability_key (tool name, resource URI, or prompt name) in
    the body rather than the URL path so that keys containing '/' (e.g.
    resource URIs like ``file:///path/to/x``) are routed correctly.
    """

    capability_key: str = Field(min_length=1, max_length=2048)


# --- MCP server status ---


class McpServerStatusOut(BaseModel):
    """Cheap per-server status, derived from persisted state (no spawn)."""

    status: Literal["healthy", "failing", "unknown"]
    # A stdio server whose launcher command does not resolve on THIS machine
    # (a synced server referencing e.g. uvx on a machine without uv). The UI
    # renders "missing <runner>" so the cause is visible.
    missing_runner: str | None = None


# --- Settings ---


class CredentialSettingsOut(BaseModel):
    """Where the credential-store master key currently lives."""

    master_key_storage: Literal["file", "keychain"] = Field(
        description="file = ~/.coffer/master.key (default); keychain = OS keychain entry."
    )


class CredentialSettingsIn(BaseModel):
    """Request body to relocate the master key."""

    master_key_storage: Literal["file", "keychain"]


class InternalEngineConfigOut(BaseModel):
    """Coffer's own operating settings: its model, and its unattended work."""

    model: str | None = None
    updated_at: datetime | None = None
    #: Keyed by pass name (``aggregate`` / ``distil`` / ``curate``); the value
    #: shape is ``internal_engine_routes.UpkeepSettingOut``, defined beside the
    #: route that builds it (this module is at its size ceiling).
    upkeep: dict[str, Any] = Field(default_factory=dict)


class InternalEngineConfigUpdate(BaseModel):
    """Set the internal-engine model; ``null``/empty clears it."""

    model: str | None = None
